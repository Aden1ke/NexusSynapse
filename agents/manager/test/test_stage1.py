"""
NexusSynapse — Manager Agent
Stage 1 Test: Environment Setup
What this tests:
    Verifies that all required environment variables are present
    and correctly loaded from the .env file.

Why this matters:
    If any credential is missing the entire agent pipeline fails.
    Catching this early saves hours of debugging.


Expected result:
    All variables show ✅ and Stage 1 PASSED prints at the bottom
"""

import os
import sys

# Add parent directory to path so we can import from run.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def test_environment_variables():
    """
    Tests that all required environment variables are loaded.
    
    Each variable is checked for presence.
    First 10 characters are shown for verification
    without exposing the full secret value.
    """
    print("="*55)
    print("  NEXUSSYNAPSE — Manager Agent")
    print("  Environment Setup")
    print("="*55)
    print()

    # Define all variables the Manager Agent needs
    # and why each one is required
    required_variables = {
        "PROJECT_CONNECTION_STRING": "Azure AI Foundry project URL",
        "MODEL_DEPLOYMENT_NAME":     "Name of deployed gpt-4o model",
        "AZURE_CLIENT_SECRET":       "Azure API authentication key",
        "GITHUB_TOKEN":              "GitHub API access token",
        "GITHUB_REPO_OWNER":         "GitHub username (Aden1ke)",
        "GITHUB_REPO_NAME":          "Repository name (NexusSynapse)",
    }

    passed = 0
    failed = 0

    for var_name, description in required_variables.items():
        value = os.getenv(var_name)

        if value:
            # Show only first 10 chars to confirm it loaded
            # without printing the full secret
            preview = value[:10] + "..." if len(value) > 10 else value
            print(f"  ✅ {var_name}")
            print(f"     Purpose: {description}")
            print(f"     Value:   {preview}")
            passed += 1
        else:
            print(f"  ❌ {var_name}")
            print(f"     Purpose: {description}")
            print(f"     Error:   NOT SET — add this to your .env file")
            failed += 1
        print()

    # Print summary
    print("-"*55)
    print(f"  Results: {passed} passed, {failed} failed")
    print()

    if failed == 0:
        print("  ✅ Stage PASSED")
        print("  Environment is correctly configured.")
        print("  Safe to proceed to Stage 2.")
    else:
        print("  ❌ Stage FAILED")
        print("  Fix the missing variables above in your .env file")
        print("  then run this test again before proceeding.")

    print("="*55)
    return failed == 0


if __name__ == "__main__":
    test_environment_variables()
