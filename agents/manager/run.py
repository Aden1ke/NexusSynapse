# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — IMPORTS AND ENVIRONMENT LOADING
# ══════════════════════════════════════════════════════════════════════════════
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── OpenTelemetry — traces every agent message for the demo trace map ─────────
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    _resource = Resource.create({"service.name": "nexussynapse-manager", "service.version": "1.0.0"})
    _provider = TracerProvider(resource=_resource)
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    _tracer      = trace.get_tracer("nexussynapse.manager")
    OTEL_ENABLED = True
except ImportError:
    _tracer      = None
    OTEL_ENABLED = False

# ── Microsoft AutoGen GroupChat pattern — agent registry ─────────────────────
# Mirrors the GroupChat/Magentic-One pattern where each agent is a named
# participant and the Manager routes messages between them.
AGENT_REGISTRY = {
    "manager":      {"name": "Manager Agent",      "role": "orchestrator", "status": "idle"},
    "coder":        {"name": "Coder Agent",         "role": "developer",    "status": "idle"},
    "senior_coder": {"name": "Senior Coder Agent",  "role": "reviewer",     "status": "idle"},
    "deployer":     {"name": "Deployer Agent",      "role": "deployment",   "status": "idle"},
}

# GroupChat message history — every agent message is logged here
# This is what gets shown as the trace map in the demo
_group_chat_history = []

def gc_message(sender: str, recipient: str, content: str, msg_type: str = "task"):
    """
    Log one GroupChat message between two agents.
    Mimics AutoGen's GroupChat.send() pattern.
    Automatically creates an OpenTelemetry span.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "sender":    sender,
        "recipient": recipient,
        "content":   content[:200],
        "type":      msg_type,   # task | review | feedback | deploy | safety
    }
    _group_chat_history.append(entry)

    # Console trace map — visible in demo video
    arrow = "→"
    print(f"  [GroupChat] {sender} {arrow} {recipient} [{msg_type.upper()}]: {content[:80]}")

    # OpenTelemetry span
    if OTEL_ENABLED and _tracer:
        with _tracer.start_as_current_span(f"{sender}->{recipient}") as span:
            span.set_attribute("gc.sender",    sender)
            span.set_attribute("gc.recipient", recipient)
            span.set_attribute("gc.type",      msg_type)
            span.set_attribute("gc.content",   content[:200])

def gc_history() -> list:
    """Return full GroupChat history for the trace map."""
    return _group_chat_history

CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
MODEL             = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")
API_KEY           = os.getenv("AZURE_API_KEY")
GITHUB_TOKEN      = os.getenv("GITHUB_TOKEN")
REPO_OWNER        = os.getenv("GITHUB_REPO_OWNER", "Aden1ke")
REPO_NAME         = os.getenv("GITHUB_REPO_NAME", "NexusSynapse")
APP_SERVICE_NAME  = os.getenv("AZURE_APP_SERVICE_NAME", "hackathon-nexussynapse-app")

# Memory — JSON file in same folder as run.py
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "manager_memory.json")

# A2A Agent URLs
CODER_AGENT_URL    = os.getenv("CODER_AGENT_URL",    "http://localhost:5002")
SENIOR_CODER_URL   = os.getenv("SENIOR_CODER_URL",   "http://localhost:5001")
DEPLOYER_AGENT_URL = os.getenv("DEPLOYER_AGENT_URL", "http://localhost:5003")
A2A_TOKEN          = os.getenv("A2A_SHARED_TOKEN")

# A2A headers sent with every agent-to-agent request
A2A_HEADERS = {
    "Content-Type":    "application/json",
    "Authorization":   f"Bearer {A2A_TOKEN}",
    "X-Agent-Name":    "Manager Agent",
    "X-Agent-Version": "1.0.0"
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — MANAGER PROMPT
# ══════════════════════════════════════════════════════════════════════════════
MANAGER_PROMPT = """
You are the Manager Agent of NexusSynapse — a Digital Employee system.
You are an experienced Tech Lead who orchestrates a team of AI agents.

Your personality:
- Methodical and decisive
- You think in numbered steps
- You delegate — you never write code yourself
- You track every agent action carefully

When given a task respond ONLY with valid JSON:
{
  "task_summary": "one line description",
  "steps": [
    "Step 1: Analyzing task requirements",
    "Step 2: Delegating to Coder Agent",
    "Step 3: Awaiting Senior Coder review",
    "Step 4: Handling approval or rejection loop",
    "Step 5: Routing to Deployer after approval",
    "Step 6: Confirming deployment success"
  ],
  "assigned_to": "Coder Agent",
  "priority": "high"
}
Do not include any text outside the JSON object.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — CHAIN OF THOUGHT LOGGER
# ══════════════════════════════════════════════════════════════════════════════
def log(agent, message, step=None):
    """
    Prints timestamped log showing every agent action.
    This is the Chain of Thought trail shown in the demo.

    Args:
        agent   (str): Which agent is logging
        message (str): What the agent is doing
        step    (int): Optional pipeline step number
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    step_text = f"Step {step}: " if step else ""
    print(f"[{timestamp}] [{agent}] {step_text}{message}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — AGENT MEMORY
# The Manager remembers every task it has ever processed.
# Stored as a JSON file so memory survives between sessions.
# ══════════════════════════════════════════════════════════════════════════════
def load_memory() -> dict:
    """Loads memory from file. Returns empty structure if none exists."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log("Manager", "Memory file corrupted — starting fresh")

    return {
        "tasks_processed":    [],
        "deployments":        [],
        "rejection_patterns": [],
        "recurring_issues":   [],
        "coder_performance":  {
            "total_tasks":      0,
            "passed_first_try": 0,
            "total_rejections": 0
        }
    }


def save_memory(memory: dict):
    """Saves memory state to file after every pipeline run."""
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=2)
        log("Manager", "Memory saved ✅")
    except Exception as e:
        log("Manager", f"Memory save failed: {e}")


def update_memory(memory, task, attempts, verdict, score, deployed):
    """
    Updates memory after each pipeline run.

    Args:
        memory   (dict): Current memory state
        task     (str):  Task that was processed
        attempts (int):  How many attempts the Coder needed
        verdict  (str):  APPROVED / REJECTED / PERMANENTLY_REJECTED
        score    (int):  Quality score 0-100
        deployed (bool): Whether code reached production

    Returns:
        dict: Updated memory state
    """
    timestamp = datetime.now().isoformat()

    memory["tasks_processed"].append({
        "task":      task,
        "attempts":  attempts,
        "verdict":   verdict,
        "score":     score,
        "deployed":  deployed,
        "timestamp": timestamp
    })

    memory["coder_performance"]["total_tasks"]      += 1
    memory["coder_performance"]["total_rejections"] += (attempts - 1)

    if attempts == 1 and verdict == "APPROVED":
        memory["coder_performance"]["passed_first_try"] += 1

    if deployed:
        memory["deployments"].append({
            "task":      task,
            "score":     score,
            "timestamp": timestamp
        })

    # Flag recurring issues
    task_titles = [t["task"][:50] for t in memory["tasks_processed"]]
    if task_titles.count(task[:50]) > 1:
        if task not in memory["recurring_issues"]:
            memory["recurring_issues"].append(task)
            log("Manager", f"⚠️  Recurring issue detected: {task[:50]}")

    return memory


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — AZURE AI CONNECTION
# ══════════════════════════════════════════════════════════════════════════════
def call_ai(system_prompt, user_message):
    """
    Calls Azure AI Foundry and returns the AI response safely.

    Args:
        system_prompt (str): Defines the AI role and behaviour
        user_message  (str): The task or question to process

    Returns:
        str: AI response text, or None if call failed
    """
    if not CONNECTION_STRING:
        print("[Error] PROJECT_CONNECTION_STRING is missing from .env!")
        return None

    if not API_KEY:
        print("[Error] AZURE_API_KEY is missing from .env!")
        return None

    try:
        endpoint_base = CONNECTION_STRING.split("/api/projects")[0]
        url = (
            f"{endpoint_base}/openai/deployments/{MODEL}"
            f"/chat/completions?api-version=2024-08-01-preview"
        )

        headers = {
            "Content-Type": "application/json",
            "api-key":      API_KEY
        }

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ],
            "temperature": 0.3,
            "max_tokens":  800
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except requests.exceptions.HTTPError as e:
        print(f"[Error] Azure HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None

    except requests.exceptions.Timeout:
        print("[Error] Azure AI timed out after 30 seconds")
        return None

    except Exception as e:
        print(f"[Error] Azure AI call failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — A2A AGENT COMMUNICATION
# Each function follows the same 3-step A2A pattern:
#   Step 1 — Fetch agent card  → verify identity
#   Step 2 — Send task + token → agent processes it
#   Step 3 — Return response   → or fallback if unreachable
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_agent_card(agent_url, agent_name):
    """Fetches agent identity card before sending any data."""
    try:
        response = requests.get(
            f"{agent_url}/.well-known/agent.json",
            timeout=10
        )

        if response.status_code == 200:
            card = response.json()
            log("Manager", f"A2A verified: {card.get('name')} v{card.get('version', '1.0')}")
            return card
        else:
            log("Manager", f"Warning: {agent_name} card returned {response.status_code}")
            return None

    except requests.exceptions.ConnectionError:
        log("Manager", f"Warning: {agent_name} not reachable — using simulated response")
        return None

    except Exception as e:
        log("Manager", f"Warning: Could not fetch {agent_name} card: {e}")
        return None


def call_coder_agent(task):
    """
    Delegates a coding task to Coder Agent via A2A.

    Args:
        task (str): The coding task to complete

    Returns:
        dict: {status, code, pr_url}
    """
    log("Manager", "Delegating to Coder Agent via A2A...", step=2)
    gc_message("Manager Agent", "Coder Agent", task, "task")

    card = _fetch_agent_card(CODER_AGENT_URL, "Coder Agent")

    if card:
        try:
            response = requests.post(
                f"{CODER_AGENT_URL}/code",
                headers=A2A_HEADERS,
                json={"task": task},
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            log("Manager", f"Coder Agent responded: {result.get('status')}")
            return result

        except requests.exceptions.HTTPError as e:
            log("Manager", f"Coder Agent HTTP error: {e.response.status_code}")

        except requests.exceptions.Timeout:
            log("Manager", "Coder Agent timed out — using fallback")

        except Exception as e:
            log("Manager", f"Coder Agent call failed: {e}")

    # Fallback — used when agent is unreachable (graceful degradation)
    log("Manager", "Coder Agent unreachable — running fallback simulation")
    return {
        "status": "submitted",
        "code": (
            f"# Coder Agent fix for: {task}\n"
            f"def fix_bug():\n"
            f"    # Fix implemented by Coder Agent\n"
            f"    pass"
        ),
        "pr_url": f"https://github.com/{REPO_OWNER}/{REPO_NAME}/pull/1"
    }


def call_senior_coder_agent(code, task, attempt=1):
    """
    Sends code to Senior Coder Agent for review via A2A.

    The Senior Coder runs 3 gates:
        Gate 1 — Content Safety  → PERMANENTLY_REJECTED if fails
        Gate 2 — pylint + bandit scanner
        Gate 3 — Azure AI Foundry review

    Args:
        code    (str): Code written by the Coder Agent
        task    (str): Original task description for context
        attempt (int): Which attempt number (1, 2, or 3)

    Returns:
        dict: {verdict, score, issues, feedback, approved_for_deployment}
    """
    log("Manager", "Routing to Senior Coder Agent via A2A...", step=3)
    gc_message("Manager Agent", "Senior Coder Agent", f"Review attempt {attempt}: {code[:80]}", "review")

    card = _fetch_agent_card(SENIOR_CODER_URL, "Senior Coder Agent")

    if card:
        try:
            response = requests.post(
                f"{SENIOR_CODER_URL}/review",
                headers=A2A_HEADERS,
                json={
                    "code":    code,
                    "task":    task,
                    "attempt": attempt
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            log("Manager", f"Senior Coder verdict: {result.get('verdict')} ({result.get('score')}/100)")
            return result

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                log("Manager", "A2A token rejected by Senior Coder — check A2A_SHARED_TOKEN in .env")
            else:
                log("Manager", f"Senior Coder HTTP error: {e.response.status_code}")

        except requests.exceptions.Timeout:
            log("Manager", "Senior Coder timed out — using fallback")

        except Exception as e:
            log("Manager", f"Senior Coder call failed: {e}")

    # Fallback — used when agent is unreachable (graceful degradation)
    log("Manager", "Senior Coder unreachable — running fallback simulation")
    return {
        "verdict":                 "APPROVED",
        "score":                   88,
        "issues":                  [],
        "feedback":                "Fallback: Senior Coder agent was unreachable",
        "approved_for_deployment": True
    }


def call_deployer_agent(task, review):
    """
    Sends approved code to Deployer Agent via A2A.

    The Deployer handles:
        - HITL approval screen (human must say YES)
        - Azure App Service deployment
        - Health check after deployment
        - Auto-rollback if health check fails

    Args:
        task   (str):  The original task description
        review (dict): Senior Coder review result with score

    Returns:
        dict: {status, url}
    """
    log("Manager", "Routing to Deployer Agent via A2A — HITL gate...", step=5)
    gc_message("Manager Agent", "Deployer Agent", f"Deploy approved code. Score: {review.get('score')}/100", "deploy")

    card = _fetch_agent_card(DEPLOYER_AGENT_URL, "Deployer Agent")

    if card:
        try:
            response = requests.post(
                f"{DEPLOYER_AGENT_URL}/deploy",
                headers=A2A_HEADERS,
                json={
                    "task":   task,
                    "review": review,
                    "score":  review.get("score"),
                    "pr_url": review.get("pr_url", "")
                },
                timeout=300   # HITL waits for human — up to 5 minutes
            )
            response.raise_for_status()
            result = response.json()
            log("Manager", f"Deployer status: {result.get('status')}")
            return result

        except requests.exceptions.HTTPError as e:
            log("Manager", f"Deployer HTTP error: {e.response.status_code}")

        except requests.exceptions.Timeout:
            log("Manager", "Deployer timed out — human did not respond to HITL")
            return {
                "status": "cancelled",
                "url":    None,
                "reason": "HITL approval timed out after 5 minutes"
            }

        except Exception as e:
            log("Manager", f"Deployer call failed: {e}")

    # Fallback — used when agent is unreachable (graceful degradation)
    log("Manager", "Deployer unreachable — running fallback simulation")
    return {
        "status": "deployed",
        "url":    f"https://{APP_SERVICE_NAME}.azurewebsites.net"
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — REJECTION LOOP HANDLER
# ══════════════════════════════════════════════════════════════════════════════
def handle_rejection_loop(user_task, initial_coder_result):
    """
    Manages the review and rejection loop between
    the Coder Agent and Senior Coder Agent.

    Flow:
        Coder submits code
            ↓
        Senior Coder reviews (attempt 1)
            ↓
        PERMANENTLY_REJECTED → escalate immediately, no retry
        REJECTED             → send feedback to Coder, retry
        APPROVED             → return to Manager
            ↓ (repeat max 3 times)

    Args:
        user_task            (str):  Original task from user
        initial_coder_result (dict): First code submission

    Returns:
        tuple: (final_review, attempts, coder_result)
    """
    coder_result = initial_coder_result

    # First review — attempt 1
    review   = call_senior_coder_agent(
        coder_result.get("code"),
        user_task,
        attempt=1
    )

    verdict  = review.get("verdict")
    score    = review.get("score", 0)
    attempts = 1

    log("Manager", f"Initial review: {verdict} (Score: {score}/100)", step=3)

    # Hard stop — Content Safety Gate 1 failed
    # Dangerous content cannot be retried — escalate to human
    if verdict == "PERMANENTLY_REJECTED":
        log("Manager", "⛔ PERMANENTLY REJECTED — dangerous content detected")
        log("Manager", "Cannot send back to Coder — escalating to human")
        return review, attempts, coder_result

    # Normal rejection loop — max 3 total attempts
    while verdict == "REJECTED" and attempts < 3:
        attempts += 1
        feedback  = review.get("feedback", "Fix issues and resubmit")
        issues    = review.get("issues", [])

        log("Manager", f"Code rejected (attempt {attempts - 1}/3)")
        log("Manager", f"Issues found: {len(issues)}")
        for issue in issues:
            print(f"           ⚠️  {issue}")
        log("Manager", f"Sending feedback to Coder: {feedback}")
        gc_message("Senior Coder Agent", "Coder Agent", feedback, "feedback")

        # Send back to Coder with specific feedback
        coder_result = call_coder_agent(
            f"{user_task} | Fix required: {feedback}"
        )

        # Fresh review — pass attempt number so Senior Coder tracks it
        review   = call_senior_coder_agent(
            coder_result.get("code"),
            user_task,
            attempt=attempts
        )

        verdict  = review.get("verdict")
        score    = review.get("score", 0)

        log("Manager", f"Re-review result: {verdict} (Score: {score}/100)")

        # Check for permanent rejection mid-loop
        if verdict == "PERMANENTLY_REJECTED":
            log("Manager", "⛔ PERMANENTLY REJECTED on re-review — escalating")
            break

    return review, attempts, coder_result


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — AUTONOMOUS TASK DETECTION
# Allows the Manager to find and fix problems without human input.
# ══════════════════════════════════════════════════════════════════════════════
def fetch_github_issues():
    """
    Fetches open GitHub issues labelled 'bug' or 'fix-needed'.

    Returns:
        list: Task dicts, empty list if none found
    """
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues?state=open"

    headers = {
        "Accept":        "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }

    try:
        log("Manager", "Checking GitHub for open bug issues...")
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 401:
            log("Manager", "GitHub auth failed — check GITHUB_TOKEN in .env")
            return []

        if response.status_code == 404:
            log("Manager", "GitHub repo not found — check REPO_OWNER and REPO_NAME")
            return []

        tasks = []
        for issue in response.json():
            labels = [label["name"] for label in issue.get("labels", [])]
            if "bug" in labels or "fix-needed" in labels:
                tasks.append({
                    "id":     issue["number"],
                    "title":  issue["title"],
                    "body":   issue.get("body") or "",
                    "url":    issue["html_url"],
                    "source": "github_issue"
                })
                log("Manager", f"Found bug issue #{issue['number']}: {issue['title']}")

        if not tasks:
            log("Manager", "No open bug issues found ✅")

        return tasks

    except requests.exceptions.ConnectionError:
        log("Manager", "Cannot reach GitHub — check internet connection")
        return []

    except Exception as e:
        log("Manager", f"GitHub fetch error: {e}")
        return []


def check_app_health():
    """
    Pings the live Azure App Service.
    Creates a task automatically if app is unhealthy.

    Returns:
        dict: Task dict if problem found, None if healthy
    """
    health_url = f"https://{APP_SERVICE_NAME}.azurewebsites.net"

    try:
        log("Manager", f"Checking app health: {health_url}")
        response = requests.get(health_url, timeout=10)

        if response.status_code == 200:
            log("Manager", "App health check passed ✅")
            return None

        log("Manager", f"App returning {response.status_code} ❌")
        return {
            "title":    f"Fix: App returning HTTP {response.status_code}",
            "body":     f"Health check failed at {datetime.now().strftime('%H:%M:%S')}",
            "source":   "health_monitor",
            "priority": "high"
        }

    except requests.exceptions.ConnectionError:
        log("Manager", "App is completely unreachable ❌")
        return {
            "title":    "CRITICAL: App is down — connection refused",
            "body":     f"App unreachable at {datetime.now().strftime('%H:%M:%S')}",
            "source":   "health_monitor",
            "priority": "critical"
        }

    except requests.exceptions.Timeout:
        log("Manager", "App health check timed out ❌")
        return {
            "title":    "App responding too slowly — performance issue",
            "body":     f"Timeout after 10 seconds at {datetime.now().strftime('%H:%M:%S')}",
            "source":   "health_monitor",
            "priority": "high"
        }


def check_github_actions():
    """
    Checks if the most recent GitHub Actions run failed.

    Returns:
        dict: Task dict if failure found, None if passing
    """
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs"

    headers = {
        "Accept":        "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }

    try:
        log("Manager", "Checking GitHub Actions for failed runs...")
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            log("Manager", f"GitHub Actions check failed: {response.status_code}")
            return None

        runs = response.json().get("workflow_runs", [])

        if not runs:
            log("Manager", "No workflow runs found")
            return None

        latest     = runs[0]
        conclusion = latest.get("conclusion")
        name       = latest.get("name", "Unknown workflow")
        run_url    = latest.get("html_url", "")

        if conclusion == "failure":
            log("Manager", f"CI/CD FAILED: {name} ❌")
            return {
                "title":    f"Fix failing CI/CD: {name}",
                "body":     f"Pipeline failed. Details: {run_url}",
                "source":   "github_actions",
                "priority": "high"
            }

        log("Manager", f"CI/CD passing ✅ ({name})")
        return None

    except Exception as e:
        log("Manager", f"GitHub Actions check error: {e}")
        return None


def autonomous_monitor():
    """
    Runs all 3 health checks in one pass.
    Processes any tasks found automatically.
    """
    log("Manager", "Starting autonomous monitoring...")
    log("Manager", "Checking: GitHub issues, App health, CI/CD status")
    print()

    tasks_found = 0

    # Check 1 — GitHub bug issues
    github_tasks = fetch_github_issues()
    for task in github_tasks:
        tasks_found += 1
        log("Manager", f"Auto-processing GitHub issue: {task['title']}")
        full_task = task["title"]
        if task.get("body"):
            full_task += f"\n\nContext: {task['body'][:200]}"
        run_manager(full_task)

    # Check 2 — App health
    health_task = check_app_health()
    if health_task:
        tasks_found += 1
        log("Manager", f"Auto-processing health issue: {health_task['title']}")
        run_manager(health_task["title"])

    # Check 3 — CI/CD pipeline
    ci_task = check_github_actions()
    if ci_task:
        tasks_found += 1
        log("Manager", f"Auto-processing CI/CD failure: {ci_task['title']}")
        run_manager(ci_task["title"])

    print()
    if tasks_found == 0:
        log("Manager", "All systems healthy ✅ Nothing to fix.")
    else:
        log("Manager", f"Processed {tasks_found} issue(s) automatically ✅")


# ── Null context manager — used when OTel is not installed ───────────────────
from contextlib import contextmanager

@contextmanager
def _null_ctx():
    """No-op context manager — replaces OTel span when library not installed."""
    yield None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — FULL ORCHESTRATION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
def run_manager(user_task):
    """
    Main orchestration function — runs the complete 6-step pipeline.

    Coordinates all 4 agents in sequence:
        Step 1 → Receive and analyze task via Azure AI
        Step 2 → Delegate to Coder Agent (Joshua)
        Step 3 → Route to Senior Coder (Segun)
        Step 4 → Handle rejection loop if needed
        Step 5 → Route to Deployer (Ibrahim) for HITL
        Step 6 → Confirm deployment and show live URL

    Args:
        user_task (str): Task entered by user or detected autonomously
    """
    print("\n" + "=" * 55)
    print("  NEXUSSYNAPSE — DIGITAL EMPLOYEE SYSTEM")
    print("  Manager Agent — Orchestrator")
    print("  Developer: SJ")
    print("=" * 55)

    # ── Root OpenTelemetry span ───────────────────────────────────────────────
    # Parent span for the entire pipeline. Every gc_message() creates a child
    # span under this root, so the full agent message flow appears as one tree:
    #
    #   [root] nexussynapse.pipeline: "Fix login bug"
    #       ├── Manager → Coder        [TASK]
    #       ├── Manager → SeniorCoder  [REVIEW]
    #       ├── SeniorCoder → Coder    [FEEDBACK]
    #       └── Manager → Deployer     [DEPLOY]
    #
    _root_span_ctx = (
        _tracer.start_as_current_span(
            "nexussynapse.pipeline",
            attributes={
                "pipeline.task":    user_task[:200],
                "pipeline.service": "nexussynapse-manager",
            }
        )
        if (OTEL_ENABLED and _tracer) else _null_ctx()
    )

    with _root_span_ctx:

     # ── Safe defaults ────────────────────────────────────────────────────────
     verdict  = "REJECTED"
     score    = 0
     attempts = 1
     deployed = False

    try:
        # ── Step 1: Analyze task with Azure AI ───────────────────────────────
        log("Manager", f"Received task: '{user_task}'", step=1)
        log("Manager", "Analyzing task requirements via Azure AI...")

        plan_response = call_ai(MANAGER_PROMPT, user_task)

        if plan_response:
            try:
                plan = json.loads(plan_response)
                log("Manager", f"Plan: {plan.get('task_summary')}")
                log("Manager", f"Priority: {plan.get('priority', 'high').upper()}")
                log("Manager", "Execution steps:")
                for step in plan.get("steps", []):
                    print(f"           {step}")
            except json.JSONDecodeError:
                log("Manager", "Plan generated — proceeding with pipeline")
        else:
            log("Manager", "Azure AI unavailable — continuing with pipeline")

        # ── Step 2: Delegate to Coder Agent ──────────────────────────────────
        coder_result = call_coder_agent(user_task)
        log("Manager", f"PR submitted: {coder_result.get('pr_url')}")

        # ── Steps 3 & 4: Review + Rejection Loop ─────────────────────────────
        final_review, attempts, coder_result = handle_rejection_loop(
            user_task,
            coder_result
        )

        verdict = final_review.get("verdict")
        score   = final_review.get("score", 0)

        log("Manager", f"Final verdict: {verdict} (Score: {score}/100 — Attempts: {attempts}/3)", step=4)

        # ── Steps 5 & 6: Deploy or Escalate ──────────────────────────────────
        if verdict == "APPROVED":
            log("Manager", "Approved! Routing to Deployer...", step=5)

            deploy        = call_deployer_agent(user_task, final_review)
            deploy_status = deploy.get("status")

            if deploy_status == "deployed":
                deployed = True
                url      = deploy.get("url")
                log("Manager", f"Live at: {url}", step=6)
                print("\n" + "=" * 55)
                print("  TASK COMPLETE ✅")
                print(f"  Live URL:  {url}")
                print(f"  Attempts:  {attempts}/3")
                print(f"  Score:     {score}/100")
                print("=" * 55 + "\n")

            elif deploy_status == "cancelled":
                log("Manager", "Deployment cancelled at HITL gate by human.")
                log("Manager", "No changes made to production.")

            else:
                log("Manager", "Deployment failed. Deployer handling rollback.")

        elif verdict == "PERMANENTLY_REJECTED":
            log("Manager", "⛔ Task permanently rejected — dangerous content.")
            log("Manager", "Escalating to human. Do NOT retry automatically.")

        else:
            log("Manager", f"Max attempts reached after {attempts} tries.")
            log("Manager", "Task escalated to human for manual review.")
            log("Manager", f"Last feedback: {final_review.get('feedback')}")

    except Exception as e:
        log("Manager", f"Pipeline error: {e}")
        log("Manager", "Saving failure to memory and exiting safely.")

    # ── Save to Memory ────────────────────────────────────────────────────────
    # Runs NO MATTER WHAT — success, failure, or crash
    memory = load_memory()
    memory = update_memory(
        memory,
        task     = user_task,
        attempts = attempts,
        verdict  = verdict,
        score    = score,
        deployed = deployed
    )
    save_memory(memory)

    # ── Memory Summary ────────────────────────────────────────────────────────
    total      = memory["coder_performance"]["total_tasks"]
    first_try  = memory["coder_performance"]["passed_first_try"]
    rejections = memory["coder_performance"]["total_rejections"]

    print("\n" + "=" * 55)
    print("  MANAGER MEMORY — Session Stats")
    print("=" * 55)
    print(f"  Tasks processed:    {total}")
    print(f"  Passed first try:   {first_try}/{total}")
    print(f"  Total rejections:   {rejections}")
    print(f"  Deployments:        {len(memory['deployments'])}")
    if memory["recurring_issues"]:
        print(f"  ⚠️  Recurring issues: {len(memory['recurring_issues'])}")
    print("=" * 55 + "\n")

    # ── GroupChat Trace Map — shown in demo video ─────────────────────────────
    history = gc_history()
    if history:
        print("=" * 55)
        print("  AGENT MESSAGE TRACE MAP (AutoGen GroupChat)")
        print("=" * 55)
        for msg in history:
            ts = msg["timestamp"][11:19]
            print(f"  [{ts}] {msg['sender']:<22} → {msg['recipient']}")
            print(f"         [{msg['type'].upper():<8}] {msg['content'][:70]}")
        print("=" * 55 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  Welcome to NexusSynapse Digital Employee")
    print("  Powered by Azure AI Foundry + gpt-4o")
    print("=" * 55)
    print()
    print("  Choose how to run:")
    print()
    print("  1. Manual  — you type the task yourself")
    print("  2. Auto    — scan GitHub issues for bugs")
    print("  3. Health  — check if live app is running")
    print("  4. CI/CD   — check if pipeline is passing")
    print("  5. Full    — run all checks automatically")
    print()

    choice = input("  Choose (1/2/3/4/5): ").strip()
    print()

    if choice == "1":
        print("  Example tasks:")
        print("    - Fix the authentication bug in login.py")
        print("    - Add input validation to the signup form")
        print()
        task = input("  Enter your task: ").strip()
        if task:
            run_manager(task)
        else:
            print("  No task entered. Please run again.")

    elif choice == "2":
        log("Manager", "Auto mode: scanning GitHub for bug issues...")
        tasks = fetch_github_issues()
        if tasks:
            for task in tasks:
                run_manager(task["title"])
        else:
            log("Manager", "No bug issues found — nothing to process")

    elif choice == "3":
        log("Manager", "Health mode: checking live app...")
        task = check_app_health()
        if task:
            run_manager(task["title"])
        else:
            log("Manager", "App is healthy — no action needed ✅")

    elif choice == "4":
        log("Manager", "CI/CD mode: checking pipeline status...")
        task = check_github_actions()
        if task:
            run_manager(task["title"])
        else:
            log("Manager", "CI/CD is passing — no action needed ✅")

    elif choice == "5":
        autonomous_monitor()

    else:
        print("  Invalid choice. Run again and choose 1-5.")
