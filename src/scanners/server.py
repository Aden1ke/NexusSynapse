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
        results = scan_code(code)
        
        # We can also log the task if needed
        # print(f"Scanning for task: {task}")
        
        return jsonify(results)
    
    except Exception as e:
        return jsonify({
            "verdict": "FAIL",
            "summary": f"Server Error: {str(e)}",
            "approved": False
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "engine": "The Gatekeeper"}), 200

if __name__ == '__main__':
    # Running on port 5000 by default
    print("🚀 Gatekeeper Scanner Server starting...")
    app.run(host='0.0.0.0', port=5000, debug=True)
