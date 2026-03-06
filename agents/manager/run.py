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
    
    # ── Rejection Loop ────────────────────────────────
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
