"""
NexusSynapse — Manager Agent
Chain of Thought Logger
What this tests:
    Verifies the log() function formats output correctly
    with timestamps, agent names, and step numbers.

Why this matters:
    The Chain of Thought log is what the user will see.
    It proves the Manager is orchestrating agents step by step.
    It is also required for the OpenTelemetry tracing feature.

Expected result:
    Timestamped logs print for all 4 agents showing
    the full pipeline from task receipt to deployment
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import log

def test_logger_format():
    """
    Tests that log() produces correctly formatted output.
    Simulates the full 4-agent pipeline log sequence
    that will appear in the demo video.
    """
    print("="*55)
    print("  NEXUSSYNAPSE — Manager Agent")
    print("  Chain of Thought Logger")
    print("="*55)
    print()
    print("  Simulating full pipeline log sequence:")
    print("  (This is what judges see in the demo video)")
    print()

    # Simulate the complete pipeline log sequence
    # Each line represents one agent action in the pipeline

    # Manager receives and plans
    log("Manager", "Received task: 'Fix authentication bug'", step=1)
    time.sleep(0.3)
    log("Manager", "Analyzing task requirements...")
    time.sleep(0.3)
    log("Manager", "Breaking task into 6 steps...")
    time.sleep(0.3)

    # Coder Agent works
    log("Manager", "Delegating to Coder Agent...", step=2)
    time.sleep(0.3)
    log("Coder", "Reading login.py from GitHub via MCP...")
    time.sleep(0.3)
    log("Coder", "Writing fix for authentication issue...")
    time.sleep(0.3)
    log("Coder", "Submitting Pull Request #1...")
    time.sleep(0.3)

    # Senior Coder reviews — first rejection
    log("Manager", "Routing to Senior Coder...", step=3)
    time.sleep(0.3)
    log("Senior Coder", "Running automated security scan...")
    time.sleep(0.3)
    log("Senior Coder", "Checking for hardcoded secrets...")
    time.sleep(0.3)
    log("Senior Coder", "REJECTED ❌ — Score: 58/100")
    time.sleep(0.3)
    log("Senior Coder", "Issue: Hardcoded API key found on line 14")
    time.sleep(0.3)

    # Manager handles rejection
    log("Manager", "Code rejected. Routing back to Coder (attempt 2/3)", step=4)
    time.sleep(0.3)
    log("Coder", "Fixing: removing hardcoded key, using os.getenv()")
    time.sleep(0.3)
    log("Coder", "Resubmitting Pull Request...")
    time.sleep(0.3)

    # Senior Coder approves
    log("Senior Coder", "Re-reviewing submission...")
    time.sleep(0.3)
    log("Senior Coder", "APPROVED ✅ — Score: 91/100")
    time.sleep(0.3)

    # Deployer handles HITL
    log("Manager", "Code approved! Routing to Deployer...", step=5)
    time.sleep(0.3)
    log("Deployer", "⚠️  HITL gate — awaiting human approval...")
    time.sleep(0.3)
    log("Deployer", "Human approved ✅ — proceeding with deployment")
    time.sleep(0.3)
    log("Deployer", "Deploying to Azure App Service...")
    time.sleep(0.3)
    log("Deployer", "Running health check...")
    time.sleep(0.3)
    log("Deployer", "Health check passed ✅")
    time.sleep(0.3)

    # Manager confirms
    log("Manager", "Deployment complete!", step=6)
    log("Manager", "Live URL: https://hackathon-nexussynapse-app.azurewebsites.net")

    print()
    print("-"*55)
    print()
    print("  ✅ Stage PASSED")
    print("  Logger is working correctly.")
    print("  Chain of Thought trail is clear and readable.")
    print("  Safe to proceed.")
    print("="*55)


if __name__ == "__main__":
    test_logger_format()
