#  Imports and environment loading 
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
MODEL = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")
API_KEY = os.getenv("AZURE_API_KEY")


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


# Simulated Agent Communication Functions 
# These functions represent calls to each teammate's agent.
# Currently simulated for testing  will be replaced with
# real HTTP calls during integration

def call_coder_agent(task):
    """
    Delegates a coding task to Coder Agent.
    
    Current: Returns simulated response for testing
    Final:   Will make HTTP request to Joshua's agent endpoint
    
    Args:
        task (str): The coding task to complete
        
    Returns:
        dict: {
            status  → "submitted" or "failed"
            code    → the code that was written
            pr_url  → link to the GitHub Pull Request
        }
    """
    log("Manager", "Delegating to Coder Agent ...", step=2)
    
    # TODO (Integration week): Replace with real call
    # response = requests.post(CODER_AGENT_URL, json={"task": task})
    # return response.json()
    
    return {
        "status": "submitted",
        "code": f"# Coder Agent fix for: {task}\ndef fix_bug():\n    # Fix implemented\n    pass",
        "pr_url": "https://github.com/Aden1ke/NexusSynapse/pull/1"
    }



def call_senior_coder_agent(code, task):
    """
    Sends code to Senior Coder Agent for security review.
    
    The Senior Coder checks for:
        - Security vulnerabilities
        - Missing error handling
        - PII exposure
        - Code quality issues
        - Logic errors
    
    Current: Returns simulated response for testing
    Final:   Will make HTTP request to Segun's agent endpoint
    
    Args:
        code (str): The code written by the Coder Agent
        task (str): Original task description for context
        
    Returns:
        dict: {
            verdict                → "APPROVED" or "REJECTED"
            score                  → quality score 0-100
            issues                 → list of problems found
            feedback               → specific fix instructions
            approved_for_deployment → True or False
        }
    """
    log("Manager", "Routing to Senior Coder Agent for review...", step=3)
    
    # TODO (Integration week): Replace with real call
    # response = requests.post(SENIOR_CODER_URL, json={"code": code, "task": task})
    # return response.json()
    
    return {
        "verdict": "APPROVED",
        "score": 88,
        "issues": [],
        "feedback": "Code is clean, secure, and well structured",
        "approved_for_deployment": True
    }



def call_deployer_agent(task, review):
    """
    Sends approved code to Deployer Agent.
    
    The Deployer Agent will:
        1. Show HITL approval screen to human
        2. Wait for YES or NO input
        3. Deploy to Azure App Service if YES
        4. Run health check after deployment
        5. Auto-rollback if health check fails
    
    Current: Returns simulated response for testing
    Final:   Will make HTTP request to Ibrahim's agent endpoint
    
    Args:
        task   (str):  The original task description
        review (dict): Senior Coder review result with score
        
    Returns:
        dict: {
            status → "deployed", "cancelled", or "failed"
            url    → live URL if deployment succeeded
        }
    """
    log("Manager", "Routing to Deployer Agent — HITL gate...", step=5)
    
    # TODO (Integration week): Replace with real call
    # response = requests.post(DEPLOYER_URL, json={"task": task, "review": review})
    # return response.json()
    
    return {
        "status": "deployed",
        "url": "https://hackathon-nexussynapse-app.azurewebsites.net"
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


# STAGE 6: System Prompt 
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

#  Entry Point
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Welcome to NexusSynapse Digital Employee")
    print("  Powered by Azure AI Foundry + gpt-4o")
    print("="*55)
    print("\nExample tasks:")
    print("  - Fix the authentication bug in login.py")
    print("  - Add input validation to the signup form")
    print("  - Refactor the database connection handler")
    print()
    task = input("Enter your task: ").strip()
    if task:
        run_manager(task)
    else:
        print("No task entered. Please run again.")
