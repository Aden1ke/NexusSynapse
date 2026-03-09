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
from datetime import datetime
from typing import Optional, Dict, Any
from flask import Flask, send_from_directory, jsonify, request, Response

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


# EMIT — push one event to the browser via SSE
def emit(level: str, agent: str, message: str, step: Optional[int] = None):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {
        "id":        str(uuid.uuid4())[:8],
        "timestamp": timestamp,
        "level":     level,
        "agent":     agent,
        "message":   f"Step {step} — {message}" if step else message
    }
    sse_queue.put(entry)
    sse_buffer.append(entry)
    if len(sse_buffer) > SSE_BUFFER_MAX:
        sse_buffer.pop(0)
    print(f"[{timestamp}] [{level.upper()}] [{agent}] {message}")

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


# REAL PIPELINE — imports run.py and patches it
def run_real_pipeline(task: str, is_unsafe: bool = False):
    try:
        import run as mgr

        # 1. Patch log() so every pipeline log → SSE → browser 
        _orig_log = mgr.log

        def patched_log(agent, message, step=None):
            _orig_log(agent, message, step)
            emit(_level(message), agent, message, step)

        mgr.log = patched_log

        # ── 2. Patch call_deployer_agent() to surface HITL in browser ─────────
        _orig_deployer = mgr.call_deployer_agent

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
        sse_buffer.clear()   # clear replay buffer so new run starts fresh
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

        # 5. Restore originals 
        mgr.log                 = _orig_log
        mgr.call_deployer_agent = _orig_deployer

    except ImportError as e:
        emit("error", "Dashboard", f"Cannot import run.py: {e}")
        emit("error", "Dashboard", "Check agents/manager/run.py exists and .env is loaded")
        pipeline_state["status"] = "complete"
    except Exception as e:
        emit("error", "Dashboard", f"Pipeline error: {e}")
        pipeline_state["status"] = "complete"


# ROUTES — serve frontend
@app.route("/")
def index():
    return send_from_directory("frontend", "dashboard.html")

@app.route("/<path:filename>")
def assets(filename):
    return send_from_directory("frontend", filename)


# ROUTES — API
@app.route("/stream")
def stream():
    """SSE endpoint — browser connects once, receives all pipeline events."""
    def generate():
        # Replay missed messages first (catches up browser that connected late)
        for entry in list(sse_buffer):
            yield f"data: {json.dumps(entry)}\n\n"
        # Then stream live
        while True:
            try:
                entry = sse_queue.get(timeout=25)
                yield f"data: {json.dumps(entry)}\n\n"
            except queue.Empty:
                yield 'data: {"heartbeat":true}\n\n'

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control":     "no-cache",
        "X-Accel-Buffering": "no",      # required for Azure App Service
        "Connection":        "keep-alive"
    })


@app.route("/api/state")
def get_state():
    return jsonify(pipeline_state)


@app.route("/api/memory")
def get_memory():
    return jsonify(load_memory())


@app.route("/api/run", methods=["POST"])
def api_run():
    if pipeline_state["status"] in ("running", "hitl_pending"):
        return jsonify({"error": "Pipeline already running"}), 400
    data = request.json or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "Task is required"}), 400
    threading.Thread(target=run_real_pipeline, args=(task, False), daemon=True).start()
    return jsonify({"status": "started", "task": task})


@app.route("/api/unsafe", methods=["POST"])
def api_unsafe():
    if pipeline_state["status"] in ("running", "hitl_pending"):
        return jsonify({"error": "Pipeline already running"}), 400
    threading.Thread(target=run_real_pipeline, args=("", True), daemon=True).start()
    return jsonify({"status": "started"})


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
    if pipeline_state["status"] in ("running", "hitl_pending"):
        return jsonify({"error": "Cannot reset while running"}), 400
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

    # Startup check — fail loudly if run.py can't be found 
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
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
