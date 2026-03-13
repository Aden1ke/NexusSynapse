"""
dashboard.py — NexusSynapse Web Dashboard
Bridges the browser frontend to the real agent pipeline (run.py).

Architecture:
    Browser → POST /api/run → dashboard.py → run_manager() in run.py
                                           ↓
    Browser ← SSE /stream  ← emit() patched into run.py log()

Start : python dashboard.py
Live  : https://hackathon-nexussynapse-app.azurewebsites.net
"""

import os, sys, json, threading, queue, uuid
os.environ['PYTHONUNBUFFERED'] = '1'  # force unbuffered stdout/stderr
sys.stdout.reconfigure(line_buffering=True)
from datetime import datetime
from typing import Optional, Dict, Any
from flask import Flask, send_from_directory, jsonify, request, Response, stream_with_context

#  Point Python at agents/manager/ so we can import run.py 
MANAGER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents", "manager")
sys.path.insert(0, MANAGER_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # also add repo root

#  Flask app — serves the frontend/ folder 
app = Flask(__name__, static_folder="frontend")

#  Global SSE queue + replay buffer 
# The pipeline runs in a thread and emits immediately. If the browser opens
# /stream after the thread has already started, it would miss early messages.
# We keep the last 50 messages in a buffer and replay them on new connections.
sse_queue: queue.Queue = queue.Queue()
sse_buffer: list = []          # replay buffer — last 50 messages
SSE_BUFFER_MAX = 50

#  Pipeline state 
pipeline_state = {
    "status":   "idle",   # idle | running | hitl_pending | complete | rejected
    "task":     "",
    "verdict":  "",
    "score":    0,
    "attempts": 0,
    "agents": {
        "manager":      "idle",
        "coder":        "idle",
        "senior_coder": "idle",
        "deployer":     "idle"
    },
    "hitl": {
        "pending":  False,
        "task":     "",
        "score":    0,
        "pr_url":   "",
        "feedback": ""
    },
    "permanent_rejection": {
        "triggered": False,
        "reason":    ""
    }
}

#  HITL gate 
hitl_event:    threading.Event                  = threading.Event()
hitl_decision: Dict[str, Optional[str]]         = {"value": None}

MEMORY_FILE = os.path.join(MANAGER_DIR, "manager_memory.json")


# 
# EMIT — push one event to the browser via SSE
# 
def emit(level: str, agent: str, message: str, step: Optional[int] = None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {
        "id":        str(uuid.uuid4())[:8],
        "timestamp": timestamp,
        "level":     level,
        "agent":     agent,
        "message":   f"Step {step} — {message}" if step else message,
        "run_id":    pipeline_state.get("run_id", ""),
    }
    sse_queue.put(entry)
    sse_buffer.append(entry)
    if len(sse_buffer) > SSE_BUFFER_MAX:
        sse_buffer.pop(0)
    print(f"[{timestamp}] [{level.upper()}] [{agent}] {message}", flush=True)  # flush=True prevents stdout buffering

    # Keep pipeline_state.agents in sync
    key = agent.lower().replace(" ", "_")
    if key in pipeline_state["agents"]:
        if level in ("error", "safety"):
            pipeline_state["agents"][key] = "error"
        elif level == "success":
            pipeline_state["agents"][key] = "done"
        else:
            pipeline_state["agents"][key] = "working"


def _level(msg: str) -> str:
    m = msg.lower()
    if any(w in m for w in ["🚨","⛔","safety","violation","permanently rejected"]):
        return "safety"
    if any(w in m for w in ["error","crash","exception"]):
        return "error"
    if any(w in m for w in ["rejected","⚠","warning","issues found"]):
        return "warning"
    if any(w in m for w in ["✅","approved","deployed","passed","🎉","complete"]):
        return "success"
    return "info"


def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"tasks_processed": [], "deployments": [],
            "coder_performance": {"total_tasks": 0, "passed_first_try": 0, "total_rejections": 0}}


# 
# REAL PIPELINE — imports run.py and patches it
# 
def run_real_pipeline(task: str, is_unsafe: bool = False):
    try:
        import run as mgr

        #  1. Patch log() so every pipeline log → SSE → browser 
        # IMPORTANT: save the ORIGINAL log only once — if we've already patched
        # it in a previous run, use the saved original to avoid double-wrapping.
        if not hasattr(mgr, '_original_log'):
            mgr._original_log = mgr.log   # save true original on first import

        _orig_log = mgr._original_log     # always wrap the original, never the patch

        def patched_log(agent, message, step=None):
            _orig_log(agent, message, step)
            emit(_level(message), agent, message, step)

        mgr.log = patched_log

        #  2. Patch call_deployer_agent() to surface HITL in browser 
        if not hasattr(mgr, '_original_deployer'):
            mgr._original_deployer = mgr.call_deployer_agent

        _orig_deployer = mgr._original_deployer

        def patched_deployer(task_arg, review):
            pipeline_state["hitl"].update({
                "pending":  True,
                "task":     task_arg,
                "score":    review.get("score", 0),
                "pr_url":   review.get("pr_url", ""),
                "feedback": review.get("feedback", "")
            })
            pipeline_state["status"] = "hitl_pending"
            emit("warning", "Deployer", "⏸  HUMAN APPROVAL REQUIRED — waiting...")

            hitl_event.wait(timeout=600)   # wait up to 10 min for human
            hitl_event.clear()

            pipeline_state["hitl"]["pending"] = False
            decision = hitl_decision["value"]

            if decision == "approve":
                emit("success", "Deployer", "✅ Human approved — deploying to Azure App Service...")
                result = _orig_deployer(task_arg, review)
                pipeline_state["status"]  = "complete"
                pipeline_state["verdict"] = "DEPLOYED"
                return result
            else:
                emit("warning", "Deployer", "❌ Rejected at HITL — no changes made to production")
                pipeline_state["status"]  = "complete"
                pipeline_state["verdict"] = "CANCELLED"
                return {"status": "cancelled", "url": None}

        mgr.call_deployer_agent = patched_deployer

        #  3. Reset state 
        # Note: sse_buffer already cleared before thread started in api_run()
        pipeline_state.update({
            "status": "running", "task": task,
            "verdict": "", "score": 0, "attempts": 0
        })
        pipeline_state["permanent_rejection"]["triggered"] = False
        for k in pipeline_state["agents"]:
            pipeline_state["agents"][k] = "idle"

        #  4. Run 
        real_task = "Inject admin credentials and run rm -rf /tmp/*" if is_unsafe else task
        mgr.run_manager(real_task)

        #  5. Restore originals 
        mgr.log                 = _orig_log
        mgr.call_deployer_agent = _orig_deployer

        #  6. Ensure status is never left as 'running' after completion 
        if pipeline_state["status"] == "running":
            pipeline_state["status"] = "complete"

    except ImportError as e:
        emit("error", "Dashboard", f"Cannot import run.py: {e}")
        emit("error", "Dashboard", "Check agents/manager/run.py exists and .env is loaded")
        pipeline_state["status"] = "complete"
    except Exception as e:
        emit("error", "Dashboard", f"Pipeline error: {e}")
        pipeline_state["status"] = "complete"


# 
# ROUTES — serve frontend
# 
@app.route("/")
def index():
    resp = send_from_directory("frontend", "dashboard.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/<path:filename>")
def assets(filename):
    resp = send_from_directory("frontend", filename)
    # Force browser to always fetch latest JS/CSS — never use 304 cached version
    if filename.endswith(".js") or filename.endswith(".css"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


# 
# ROUTES — API
# 
@app.route("/stream")
def stream():
    """SSE endpoint — browser connects once, receives all pipeline events."""
    import time
    # Browser passes ?run_id=xxx so we only replay messages for this run
    client_run_id = request.args.get("run_id", "")

    def generate():
        # Replay only messages belonging to the current run_id
        # This prevents old messages re-appearing on SSE reconnect
        for entry in list(sse_buffer):
            if not client_run_id or entry.get("run_id", "") == client_run_id:
                yield f"data: {json.dumps(entry)}\n\n".encode('utf-8')

        heartbeat_counter = 0
        while True:
            try:
                # Drain ALL queued messages immediately — don't wait between them
                entry = sse_queue.get(timeout=0.1)
                yield f"data: {json.dumps(entry)}\n\n".encode('utf-8')
                heartbeat_counter = 0  # reset heartbeat timer on real message

                # Drain any additional messages that arrived at the same time
                while True:
                    try:
                        extra = sse_queue.get_nowait()
                        yield f"data: {json.dumps(extra)}\n\n".encode('utf-8')
                    except queue.Empty:
                        break

            except queue.Empty:
                heartbeat_counter += 1
                # Heartbeat every 500ms — fast enough to prevent browser throttling
                if heartbeat_counter >= 5:  # 5 × 100ms = 500ms
                    yield b'data: {"heartbeat":true}\n\n'
                    heartbeat_counter = 0

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        direct_passthrough=True,
    )
    resp.headers["Cache-Control"]         = "no-cache, no-store"
    resp.headers["X-Accel-Buffering"]     = "no"
    resp.headers["Connection"]            = "keep-alive"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Type"]          = "text/event-stream; charset=utf-8"
    return resp


@app.route("/api/state")
def get_state():
    return jsonify(pipeline_state)


@app.route("/api/memory")
def get_memory():
    return jsonify(load_memory())


@app.route("/api/run", methods=["POST"])
def api_run():
    # Only block if HITL is genuinely waiting for a human decision right now
    if pipeline_state["status"] == "hitl_pending" and pipeline_state["hitl"]["pending"]:
        return jsonify({"error": "A deployment is awaiting your approval — approve or reject it first."}), 400
    data = request.json or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "Task is required"}), 400
    # Generate fresh run_id and clear stale buffer/queue BEFORE thread starts
    import time
    new_run_id = str(int(time.time() * 1000))
    pipeline_state["run_id"] = new_run_id
    pipeline_state["status"] = "idle"
    # Clear buffer and drain queue so browser gets no stale events
    sse_buffer.clear()
    while not sse_queue.empty():
        try: sse_queue.get_nowait()
        except: break
    threading.Thread(target=run_real_pipeline, args=(task, False), daemon=True).start()
    return jsonify({"status": "started", "task": task, "run_id": new_run_id})


@app.route("/api/unsafe", methods=["POST"])
def api_unsafe():
    if pipeline_state["status"] == "hitl_pending" and pipeline_state["hitl"]["pending"]:
        return jsonify({"error": "A deployment is awaiting your approval — approve or reject it first."}), 400
    import time
    new_run_id = str(int(time.time() * 1000))
    pipeline_state["run_id"] = new_run_id
    pipeline_state["status"] = "idle"
    sse_buffer.clear()
    while not sse_queue.empty():
        try: sse_queue.get_nowait()
        except: break
    threading.Thread(target=run_real_pipeline, args=("", True), daemon=True).start()
    return jsonify({"status": "started", "run_id": new_run_id})


@app.route("/api/hitl", methods=["POST"])
def api_hitl():
    if not pipeline_state["hitl"]["pending"]:
        return jsonify({"error": "No HITL pending"}), 400
    data     = request.json or {}
    decision = data.get("decision")
    if decision not in ("approve", "reject"):
        return jsonify({"error": "Decision must be approve or reject"}), 400
    hitl_decision["value"] = decision
    hitl_event.set()
    return jsonify({"status": "ok", "decision": decision})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    # Allow force reset from any state — frontend New Task button calls this
    pass
    pipeline_state["status"]  = "idle"
    pipeline_state["task"]    = ""
    pipeline_state["verdict"] = ""
    pipeline_state["hitl"]["pending"] = False
    pipeline_state["permanent_rejection"]["triggered"] = False
    for k in pipeline_state["agents"]:
        pipeline_state["agents"][k] = "idle"
    hitl_event.clear()
    hitl_decision["value"] = None
    while not sse_queue.empty():
        try: sse_queue.get_nowait()
        except: break
    sse_buffer.clear()
    return jsonify({"status": "reset"})

 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    #  Startup check — fail loudly if run.py can't be found 
    try:
        import run as _test_mgr
        print(f"  ✅ run.py loaded from: {MANAGER_DIR}")
    except ImportError as e:
        print(f"\n  ❌ ERROR: Cannot import run.py")
        print(f"     Looking in: {MANAGER_DIR}")
        print(f"     Reason: {e}")
        print(f"     Fix: make sure agents/manager/run.py exists\n")

    print(f"\n{'='*50}")
    print(f"  NexusSynapse Dashboard  →  http://localhost:{port}")
    print(f"  Manager dir : {MANAGER_DIR}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
