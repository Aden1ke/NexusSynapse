from flask import Flask, request, jsonify
import sys
import os

# Ensure we can import from the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from security_scanner import scan_code

app = Flask(__name__)

@app.route('/review', methods=['POST'])
def review_code():
    """
    Endpoint for code review.
    Expected JSON: {"code": "...", "task": "..."}
    """
    # Verify A2A token
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {os.getenv('A2A_SHARED_TOKEN')}":
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()

    if not data or 'code' not in data:
        return jsonify({
            "verdict": "FAIL",
            "summary": "Invalid payload: 'code' field is required.",
            "approved": False
        }), 400

    code = data.get('code')
    task = data.get('task', 'No task description provided.')

    try:
        # Pass the code to our scanning engine
        results = scan_code(code, task=task)
        
        # Consolidate issues into the requested format: {"line": X, "msg": "..."}
        issues = []
        details = results.get("details", {})
        
        # Process lint issues
        for issue in details.get("lint", []):
            issues.append({"line": issue.get("line"), "msg": issue.get("message")})
            
        # Process security issues
        for issue in details.get("security", []):
            issues.append({"line": issue.get("line"), "msg": issue.get("message")})
            
        results["issues"] = issues
        
        return jsonify(results)
    
    except Exception as e:
        return jsonify({
            "verdict": "FAIL",
            "summary": f"Server Error: {str(e)}",
            "approved": False
        }), 500

@app.route('/.well-known/agent.json', methods=['GET'])
def agent_card():
    """
    Returns the agent's identity card for discovery.
    """
    return jsonify({
        "name": "Senior Coder Agent",
        "version": "1.0.0",
        "description": "The Gatekeeper — 3-gate code review",
        "endpoint": "/review",
        "port": 5001
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "engine": "The Gatekeeper"}), 200

if __name__ == '__main__':
    # Running on port 5001 by default
    print("🚀 Gatekeeper Scanner Server starting...")
    app.run(host='0.0.0.0', port=5001, debug=True)
