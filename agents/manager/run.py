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


