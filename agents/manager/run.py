#  Imports and environment loading 
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
MODEL             = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")
API_KEY           = os.getenv("AZURE_API_KEY")
GITHUB_TOKEN      = os.getenv("GITHUB_TOKEN")
REPO_OWNER        = os.getenv("GITHUB_REPO_OWNER", "Aden1ke")
REPO_NAME         = os.getenv("GITHUB_REPO_NAME", "NexusSynapse")
APP_SERVICE_NAME  = os.getenv("AZURE_APP_SERVICE_NAME", "hackathon-nexussynapse-app")

#  A2A Agent URLs
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


#  Chain of Thought Logger 
def log(agent, message, step=None):
    """
    Prints timestamped log showing every agent action.
    This is the Chain of Thought trail shown in the demo.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    step_text = f"Step {step}: " if step else ""
    print(f"[{timestamp}] [{agent}] {step_text}{message}")


def call_ai(system_prompt, user_message):
    """Calls Azure AI Foundry and returns the AI response safely."""
    
    # SAFETY CHECK
    if not CONNECTION_STRING:
        print("[Error] PROJECT_CONNECTION_STRING is missing from .env!")
        return None

    try:
        # 2. ENDPOINT PARSING: Safely extract the base URL
        # split by the API path to isolate the host address
        endpoint_base = CONNECTION_STRING.split("/api/projects")[0]
        url = f"{endpoint_base}/openai/deployments/{MODEL}/chat/completions?api-version=2024-08-01-preview"

        # 3. REQUEST SETUP
        headers = {
            "Content-Type": "application/json",
            "api-key": API_KEY
        }

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "max_tokens": 800
        }

        # 4. EXECUTION
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        # Raise an error if the HTTP request failed (e.g., 401 Unauthorized)
        response.raise_for_status() 

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print(f"[Error] Azure AI call failed: {e}")
        return None

# SECTION 4 — A2A AGENT COMMUNICATION
# Each function follows the same 3-step A2A pattern:
#
#   Step 1 — Fetch the agent's card (/.well-known/agent.json)
#            This verifies we are talking to the right agent
#            Like checking someone's ID before letting them in
#
#   Step 2 — Send the task with A2A token in the header
#            The token proves this request came from the Manager
#            Each agent checks this token before processing
#
#   Step 3 — Return the response OR fallback if agent is unreachable
#            Fallback keeps the pipeline running during testing
#            when teammates' agents are not running yet
#
# During testing:  agents run on localhost ports
# During demo:     agents run on Azure App Service URLs


def _fetch_agent_card(agent_url, agent_name):
    """
    Fetches and verifies an agent's identity card.
    Every A2A call starts here before sending any data.

    The Agent Card lives at: {agent_url}/.well-known/agent.json
    It tells us:
        - The agent's name and version
        - What it can do (capabilities)
        - What format it expects (input/output schema)

    Args:
        agent_url  (str): Base URL of the agent
        agent_name (str): Human readable name for logging

    Returns:
        dict: The agent card, or None if unreachable
    """
    try:
        card_url  = f"{agent_url}/.well-known/agent.json"
        response  = requests.get(card_url, timeout=10)

        if response.status_code == 200:
            card = response.json()
            log("Manager", f"A2A verified: {card.get('name')} v{card.get('version', '1.0')}")
            return card
        else:
            log("Manager", f"Warning: {agent_name} card returned {response.status_code}")
            return None

    except requests.exceptions.ConnectionError:
        # Agent is not running yet — this is normal during testing
        log("Manager", f"Warning: {agent_name} not reachable — using simulated response")
        return None

    except Exception as e:
        log("Manager", f"Warning: Could not fetch {agent_name} card: {e}")
        return None


def call_coder_agent(task):
    """
    Delegates a coding task to Coder Agent via A2A.

    A2A Flow:
        1. Fetch Coder Agent card  → verify identity
        2. POST task with A2A token → agent processes it
        3. Receive code + PR URL   → pass to Senior Coder

    Falls back to simulated response if agent is unreachable.
    Remove fallback after integration week when Joshua's
    agent is running on Azure.

    Args:
        task (str): The coding task to complete

    Returns:
        dict: {
            status  → "submitted" or "failed"
            code    → the code that was written
            pr_url  → link to the GitHub Pull Request
        }
    """
    log("Manager", "Delegating to Coder Agent via A2A...", step=2)

    # Step 1 — Verify Coder Agent identity
    card = _fetch_agent_card(CODER_AGENT_URL, "Coder Agent")

    # Step 2 — Send task if agent is reachable
    if card:
        try:
            response = requests.post(
                f"{CODER_AGENT_URL}/code",
                headers=A2A_HEADERS,
                json={"task": task},
                timeout=60   # coding takes longer than a health check
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

    # Step 3 — Fallback: simulated response
    # Used when Joshua's agent is not running yet
    # TODO: Remove this fallback after March 12 integration
    log("Manager", "Using simulated Coder response (integration pending)")
    return {
        "status": "submitted",
        "code":   (
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

    A2A Flow:
        1. Fetch Senior Coder card → verify identity
        2. POST code with A2A token → agent reviews it
        3. Receive verdict + score  → pass to rejection loop

    The Senior Coder runs 3 checks:
        - pylint + bandit scanner  (Gate 2)
        - Azure AI Foundry review  (Gate 3)
        - Content Safety guardrails (Gate 1)

    Falls back to simulated response if agent is unreachable.

    Args:
        code    (str): The code written by the Coder Agent
        task    (str): Original task description for context
        attempt (int): Which attempt number (1, 2, or 3)

    Returns:
        dict: {
            verdict                 → "APPROVED" / "REJECTED" / "PERMANENTLY_REJECTED"
            score                   → quality score 0-100
            issues                  → list of problems found
            feedback                → specific fix instructions
            approved_for_deployment → True or False
        }
    """
    log("Manager", "Routing to Senior Coder Agent via A2A...", step=3)

    # Step 1 — Verify Senior Coder Agent identity
    card = _fetch_agent_card(SENIOR_CODER_URL, "Senior Coder Agent")

    # Step 2 — Send code for review if agent is reachable
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
                timeout=60   # AI review takes time
            )
            response.raise_for_status()
            result = response.json()
            log("Manager", f"Senior Coder verdict: {result.get('verdict')} ({result.get('score')}/100)")
            return result

        except requests.exceptions.HTTPError as e:
            # 403 means A2A token was rejected — token mismatch
            if e.response.status_code == 403:
                log("Manager", "A2A token rejected by Senior Coder — check A2A_SHARED_TOKEN in .env")
            else:
                log("Manager", f"Senior Coder HTTP error: {e.response.status_code}")

        except requests.exceptions.Timeout:
            log("Manager", "Senior Coder timed out — using fallback")

        except Exception as e:
            log("Manager", f"Senior Coder call failed: {e}")

    # Step 3 — Fallback: simulated response
    # TODO: Remove this fallback after March 12 integration
    log("Manager", "Using simulated Senior Coder response (integration pending)")
    return {
        "verdict":                "APPROVED",
        "score":                  88,
        "issues":                 [],
        "feedback":               "Simulated review — Senior Coder agent not yet connected",
        "approved_for_deployment": True
    }


def call_deployer_agent(task, review):
    """
    Sends approved code to Deployer Agent via A2A.

    A2A Flow:
        1. Fetch Deployer Agent card → verify identity
        2. POST task + review        → agent shows HITL screen
        3. Human approves or cancels → agent deploys or stops
        4. Receive deployment status → confirm live URL

    The Deployer handles:
        - HITL approval screen (human must say YES)
        - Azure App Service deployment
        - Health check after deployment
        - Auto-rollback if health check fails

    Falls back to simulated response if agent is unreachable.

    Args:
        task   (str):  The original task description
        review (dict): Senior Coder review result with score

    Returns:
        dict: {
            status → "deployed", "cancelled", or "failed"
            url    → live URL if deployment succeeded
        }
    """
    log("Manager", "Routing to Deployer Agent via A2A — HITL gate...", step=5)

    # Step 1 — Verify Deployer Agent identity
    card = _fetch_agent_card(DEPLOYER_AGENT_URL, "Deployer Agent")

    # Step 2 — Send deployment request if agent is reachable
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
                # Long timeout — HITL waits for human input
                # Human has up to 5 minutes to approve or reject
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            log("Manager", f"Deployer status: {result.get('status')}")
            return result

        except requests.exceptions.HTTPError as e:
            log("Manager", f"Deployer HTTP error: {e.response.status_code}")

        except requests.exceptions.Timeout:
            # HITL timed out — human did not respond in 5 minutes
            log("Manager", "Deployer timed out — human did not respond to HITL prompt")
            return {
                "status": "cancelled",
                "url":    None,
                "reason": "HITL approval timed out after 5 minutes"
            }

        except Exception as e:
            log("Manager", f"Deployer call failed: {e}")

    # Step 3 — Fallback: simulated response
    # TODO: Remove this fallback after March 12 integration
    log("Manager", "Using simulated Deployer response (integration pending)")
    return {
        "status": "deployed",
        "url":    f"https://{APP_SERVICE_NAME}.azurewebsites.net"
    }


#  Rejection Loop Handler
def handle_rejection_loop(user_task, initial_coder_result):
    """
    Manages the review and rejection loop between
    the Coder Agent and Senior Coder Agent.
    
    Flow:
        Coder submits code
            ↓
        Senior Coder reviews
            ↓ (if rejected)
        Feedback sent back to Coder
            ↓
        Coder fixes and resubmits
            ↓ (repeat max 3 times)
        Senior Coder approves
            ↓
        Return approved code to Manager
    
    Args:
        user_task           (str):  Original task from user
        initial_coder_result (dict): First code submission
        
    Returns:
        tuple: (final_review, attempts, coder_result)
            final_review → the final Senior Coder verdict
            attempts     → how many attempts were needed
            coder_result → the final approved code
    """
    # Start with the first code submission
    coder_result = initial_coder_result
    
    # Get first review from Senior Coder
    review = call_senior_coder_agent(
        coder_result.get("code"),
        user_task
    )
    
    verdict = review.get("verdict")
    score = review.get("score")
    attempts = 1
    
    log("Manager", f"Initial review: {verdict} (Score: {score}/100)", step=3)
    
    # Rejection Loop
    # Keep sending back to Coder until approved or max attempts
    # Max 3 attempts prevents infinite loop if code is unfixable
    while verdict == "REJECTED" and attempts < 3:
        attempts += 1
        feedback = review.get("feedback")
        issues = review.get("issues", [])
        
        # Log the rejection details
        log("Manager", f"Code rejected (attempt {attempts-1}/3)")
        log("Manager", f"Issues found: {len(issues)}")
        for issue in issues:
            print(f"           ⚠️  {issue}")
        log("Manager", f"Sending feedback to Coder: {feedback}")
        
        # Send back to Coder with specific feedback
        # Coder must fix ONLY the issues raised — nothing else
        coder_result = call_coder_agent(
            f"{user_task} | Fix required: {feedback}"
        )
        
        # Get fresh review of the revised code
        review = call_senior_coder_agent(
            coder_result.get("code"),
            user_task
        )
        
        verdict = review.get("verdict")
        score = review.get("score")
        
        log("Manager", f"Re-review result: {verdict} (Score: {score}/100)")
    
    return review, attempts, coder_result



# AUTONOMOUS TASK DETECTION
# These functions allow the Manager to find and fix
# problems WITHOUT a human typing a task.
#
# How it works:
#   1. Manager checks GitHub for open bug issues
#   2. Manager checks if the live app is healthy
#   3. Manager checks if CI/CD pipeline failed
#   4. If any problem found → run_manager() automatically
#
# it detects and fixes problems on its own.

def fetch_github_issues():
    """
    Fetches open GitHub issues labelled 'bug' or 'fix-needed'.
    Manager reads these as tasks — no human needed.

    How GitHub Issues become agent tasks:
        Someone reports a bug on GitHub
            ↓
        Manager detects it automatically
            ↓
        Full pipeline runs (Coder → Senior Coder → Deployer)
            ↓
        Bug fixed without anyone typing a command

    Returns:
        list: List of task dictionaries, empty list if none found
        Each task has:
            id     → GitHub issue number
            title  → becomes the task description
            body   → extra context for the Coder Agent
            url    → link back to the GitHub issue
            source → "github_issue" (so we know where it came from)
    """
    # Read GitHub credentials from .env
    github_token = os.getenv("GITHUB_TOKEN")
    repo_owner = os.getenv("GITHUB_REPO_OWNER", "Aden1ke")
    repo_name = os.getenv("GITHUB_REPO_NAME", "NexusSynapse")

    # GitHub REST API endpoint for listing issues
    # state=open means only unfixed issues
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues?state=open"

    headers = {
        # GitHub requires this Accept header for their API
        "Accept": "application/vnd.github.v3+json",
        # Bearer token authentication
        "Authorization": f"Bearer {github_token}"
    }

    try:
        log("Manager", "Checking GitHub for open bug issues...")
        response = requests.get(url, headers=headers, timeout=30)

        # 401 means token is wrong or expired
        if response.status_code == 401:
            log("Manager", "GitHub auth failed — check GITHUB_TOKEN in .env")
            return []

        # 404 means repo not found or private
        if response.status_code == 404:
            log("Manager", "GitHub repo not found — check GITHUB_REPO_OWNER and GITHUB_REPO_NAME")
            return []

        # Parse the JSON list of issues
        issues = response.json()

        # Filter — only process issues labelled 'bug' or 'fix-needed'
        # We don't want to process feature requests or questions
        tasks = []
        for issue in issues:
            # Get list of label names for this issue
            # Each label is a dict like {"name": "bug", "color": "red"}
            labels = [label["name"] for label in issue.get("labels", [])]

            # Only process bug issues
            if "bug" in labels or "fix-needed" in labels:
                tasks.append({
                    "id": issue["number"],
                    "title": issue["title"],
                    # body can be None if issue has no description
                    "body": issue.get("body") or "",
                    "url": issue["html_url"],
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
    Pings the live Azure App Service to check if it is running.
    If the app is down or returning errors — creates a task automatically.

    This is called Self-Healing:
        App goes down
            ↓
        Manager detects it
            ↓
        Manager creates a fix task
            ↓
        Deployer rolls back or redeploys

    Returns:
        dict: A task dictionary if problem found, None if healthy
    """
    # The URL of our live app
    app_name = os.getenv("AZURE_APP_SERVICE_NAME", "hackathon-nexussynapse-app")
    health_url = f"https://{app_name}.azurewebsites.net"

    try:
        log("Manager", f"Checking app health: {health_url}")

        # Short timeout — health check should be fast
        # If app takes more than 10 seconds to respond something is wrong
        response = requests.get(health_url, timeout=10)

        if response.status_code == 200:
            log("Manager", "App health check passed ✅")
            return None  # None means no task needed

        else:
            # App responded but with an error status
            log("Manager", f"App returning {response.status_code} ❌")
            return {
                "title": f"Fix: App returning HTTP {response.status_code}",
                "body": f"Health check failed at {datetime.now().strftime('%H:%M:%S')}. Status: {response.status_code}",
                "source": "health_monitor",
                "priority": "high"
            }

    except requests.exceptions.ConnectionError:
        # App is completely unreachable
        log("Manager", "App is completely unreachable ❌")
        return {
            "title": "CRITICAL: App is down — connection refused",
            "body": f"App unreachable at {datetime.now().strftime('%H:%M:%S')}",
            "source": "health_monitor",
            "priority": "critical"
        }

    except requests.exceptions.Timeout:
        # App took too long to respond
        log("Manager", "App health check timed out ❌")
        return {
            "title": "App responding too slowly — performance issue",
            "body": f"Timeout after 10 seconds at {datetime.now().strftime('%H:%M:%S')}",
            "source": "health_monitor",
            "priority": "high"
        }


def check_github_actions():
    """
    Checks if the most recent GitHub Actions workflow run failed.
    If CI/CD pipeline is broken — creates a fix task automatically.

    Why this matters:
        Tests fail in CI/CD
            ↓
        Manager detects failure
            ↓
        Coder Agent fixes the failing tests
            ↓
        Pipeline goes green again

    Returns:
        dict: A task dictionary if failure found, None if all passing
    """
    github_token = os.getenv("GITHUB_TOKEN")
    repo_owner = os.getenv("GITHUB_REPO_OWNER", "Aden1ke")
    repo_name = os.getenv("GITHUB_REPO_NAME", "NexusSynapse")

    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}"
    }

    try:
        log("Manager", "Checking GitHub Actions for failed runs...")
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            log("Manager", f"GitHub Actions check failed: {response.status_code}")
            return None

        data = response.json()
        # workflow_runs is a list of recent pipeline runs
        runs = data.get("workflow_runs", [])

        if not runs:
            log("Manager", "No workflow runs found")
            return None

        # Check the most recent run only
        latest = runs[0]

        # conclusion can be: success, failure, cancelled, skipped
        conclusion = latest.get("conclusion")
        workflow_name = latest.get("name", "Unknown workflow")
        run_url = latest.get("html_url", "")

        if conclusion == "failure":
            log("Manager", f"CI/CD FAILED: {workflow_name} ❌")
            return {
                "title": f"Fix failing CI/CD: {workflow_name}",
                "body": f"Pipeline failed. Details: {run_url}",
                "source": "github_actions",
                "priority": "high"
            }

        elif conclusion == "success":
            log("Manager", f"CI/CD passing ✅ ({workflow_name})")
            return None

        else:
            # Still running or was cancelled — not a problem
            log("Manager", f"CI/CD status: {conclusion} — no action needed")
            return None

    except Exception as e:
        log("Manager", f"GitHub Actions check error: {e}")
        return None


def autonomous_monitor():
    """
    Runs all health checks in one pass.
    Finds tasks automatically then runs the full pipeline.

    In 'watch' mode this loops every 5 minutes forever.
    In 'scan' mode this runs once and exits.

    Args:
        watch (bool): True = loop forever, False = run once
    """
    import time

    log("Manager", "Starting autonomous monitoring...")
    log("Manager", "Checking: GitHub issues, App health, CI/CD status")
    print()

    # Track if we found anything to fix
    tasks_found = 0

    # Check 1: GitHub bug issues 
    github_tasks = fetch_github_issues()
    for task in github_tasks:
        tasks_found += 1
        log("Manager", f"Auto-processing GitHub issue: {task['title']}")
        # Build a complete task description from title + body
        full_task = task["title"]
        if task.get("body"):
            full_task += f"\n\nContext: {task['body'][:200]}"
        run_manager(full_task)

    #Check 2: App health
    health_task = check_app_health()
    if health_task:
        tasks_found += 1
        log("Manager", f"Auto-processing health issue: {health_task['title']}")
        run_manager(health_task["title"])

    # Check 3: CI/CD pipeline 
    ci_task = check_github_actions()
    if ci_task:
        tasks_found += 1
        log("Manager", f"Auto-processing CI/CD failure: {ci_task['title']}")
        run_manager(ci_task["title"])

    # Summary 
    print()
    if tasks_found == 0:
        log("Manager", "All systems healthy ✅ Nothing to fix.")
    else:
        log("Manager", f"Processed {tasks_found} issue(s) automatically ")

# Full Orchestration Pipeline 
def run_manager(user_task):
    """
    Main orchestration function — runs the complete pipeline.
    
    This coordinates all 4 agents in sequence:
        Step 1 → Receive and analyze task via Azure AI
        Step 2 → Delegate to Coder Agent (Joshua)
        Step 3 → Route to Senior Coder (Segun)
        Step 4 → Handle rejection loop if needed
        Step 5 → Route to Deployer (Ibrahim) for HITL
        Step 6 → Confirm deployment and show live URL
    
    Args:
        user_task (str): Task entered by the user
    """
    print("\n" + "="*55)
    print("  NEXUSSYNAPSE — DIGITAL EMPLOYEE SYSTEM")
    print("  Manager Agent — Orchestrator")
    print("  Developer: SJ")
    print("="*55)

    #  Step 1: Analyze task with Azure AI 
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

    # Step 2: Delegate to Coder Agent 
    coder_result = call_coder_agent(user_task)
    log("Manager", f"PR submitted: {coder_result.get('pr_url')}")

    #  Steps 3 & 4: Review + Rejection Loop 
    final_review, attempts, coder_result = handle_rejection_loop(
        user_task,
        coder_result
    )

    verdict = final_review.get("verdict")
    score = final_review.get("score")

    log("Manager", f"Final verdict: {verdict} (Score: {score}/100 — Attempts: {attempts})", step=4)

    #  Steps 5 & 6: Deploy or Escalate 
    if verdict == "APPROVED":
        log("Manager", "Approved! Routing to Deployer...", step=5)

        deploy = call_deployer_agent(user_task, final_review)
        deploy_status = deploy.get("status")

        if deploy_status == "deployed":
            url = deploy.get("url")
            log("Manager", f"Live at: {url}", step=6)
            print("\n" + "="*55)
            print("  TASK COMPLETE ✅")
            print(f"  Live URL:  {url}")
            print(f"  Attempts:  {attempts}/3")
            print(f"  Score:     {score}/100")
            print("="*55 + "\n")

        elif deploy_status == "cancelled":
            log("Manager", "Deployment cancelled at HITL gate by human.")
            log("Manager", "No changes made to production.")

        else:
            log("Manager", "Deployment failed. Deployer handling rollback.")

    else:
        log("Manager", f"Max attempts reached after {attempts} tries.")
        log("Manager", "Task escalated to human for manual review.")
        log("Manager", f"Last feedback: {final_review.get('feedback')}")


#  Entry Point
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Welcome to NexusSynapse Digital Employee")
    print("  Powered by Azure AI Foundry + gpt-4o")
    print("="*55)
    print()
    print("  Choose how to run:")
    print()

    # Mode 1: Human types a task manually
    print("  1. Manual  — you type the task yourself")

    # Mode 2: Manager reads GitHub issues automatically
    print("  2. Auto    — scan GitHub issues for bugs")

    # Mode 3: Manager checks app health
    print("  3. Health  — check if live app is running")

    # Mode 4: Manager checks CI/CD pipeline
    print("  4. CI/CD   — check if pipeline is passing")

    # Mode 5: All checks at once
    print("  5. Full    — run all checks automatically")

    print()
    choice = input("  Choose (1/2/3/4/5): ").strip()
    print()

    if choice == "1":
        # Original manual mode
        print("Example tasks:")
        print("  - Fix the authentication bug in login.py")
        print("  - Add input validation to the signup form")
        print()
        task = input("Enter your task: ").strip()
        if task:
            run_manager(task)
        else:
            print("No task entered. Please run again.")

    elif choice == "2":
        # Autonomous GitHub issue mode
        log("Manager", "Auto mode: scanning GitHub for bug issues...")
        tasks = fetch_github_issues()
        if tasks:
            for task in tasks:
                run_manager(task["title"])
        else:
            log("Manager", "No bug issues found — nothing to process")

    elif choice == "3":
        # App health check mode
        log("Manager", "Health mode: checking live app...")
        task = check_app_health()
        if task:
            run_manager(task["title"])
        else:
            log("Manager", "App is healthy — no action needed ✅")

    elif choice == "4":
        # CI/CD check mode
        log("Manager", "CI/CD mode: checking pipeline status...")
        task = check_github_actions()
        if task:
            run_manager(task["title"])
        else:
            log("Manager", "CI/CD is passing — no action needed ✅")

    elif choice == "5":
        # Full autonomous scan
        autonomous_monitor()

    else:
        print("Invalid choice. Run again and choose 1-5.")
