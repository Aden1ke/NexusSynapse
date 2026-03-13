"""
Entry point for the Coder Agent — Builder Agent.
Save as: agents/coder/run.py
Run with: python agents/coder/run.py  (from repo root)
"""
import os
import sys

# Allow imports from repo root regardless of where script is run from
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from dotenv import load_dotenv
load_dotenv()

from agents.coder.agent import BuilderAgent, create_a2a_server

if __name__ == '__main__':
    print()
    print("=" * 55)
    print("  NexusSynapse — Coder Agent (Builder)")
    print("  Developer : Joshua")
    print("  Port      : 5002")
    print("  Endpoint  : POST /code")
    print("=" * 55)

    # Check required env vars before starting
    required = ["PROJECT_CONNECTION_STRING", "AZURE_API_KEY", "A2A_SHARED_TOKEN",
                "GITHUB_TOKEN", "GITHUB_REPO_OWNER", "GITHUB_REPO_NAME"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print()
        print("  Missing required env vars:")
        for v in missing:
            print(f"     {v}")
        print()
        print("  Add them to .env and restart.")
        print()
        sys.exit(1)

    print()
    print("  All required env vars present")
    print(f"  A2A token: set")
    print(f"  GitHub repo: {os.environ.get('GITHUB_REPO_OWNER')}/{os.environ.get('GITHUB_REPO_NAME')}")
    print(f"  Senior Coder URL: {os.environ.get('SENIOR_CODER_URL', 'http://localhost:5001')}")
    print()
    print("  Starting server...")
    print()

    agent = BuilderAgent()
    app   = create_a2a_server(agent)
    app.run(host='0.0.0.0', port=5002, debug=False)
