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
