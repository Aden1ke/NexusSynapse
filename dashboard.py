"""
dashboard.py  b start python web server to handle signup
"""

import os, sys, json, threading, queue, uuid
os.environ['PYTHONUNBUFFERED'] = '1'  # force unbuffered stdout/stderr
sys.stdout.reconfigure(line_buffering=True)
from datetime import datetime
from typing import Optional, Dict, Any
from flask import Flask, send_from_directory, jsonify, request, Response, stream_with_context, session
from flask_bcrypt import Bcrypt

# User database simulation
users_db = {}

# New user model with password hashing
def create_user(username, password):
    if username in users_db:
        return False, "User already exists."
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    users_db[username] = hashed_password
    return True, "User created successfully."

# Check user's hashed password
def authenticate_user(username, password):
    if username not in users_db:
        return False
    return bcrypt.check_password_hash(users_db[username], password)

#  Flask app  b serves the frontend/ folder 
app = Flask(__name__, static_folder="frontend")
app.config['SECRET_KEY'] = 'A very complex secret key'

bcrypt = Bcrypt(app)

# Signup route that handles form submission
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.form
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    success, message = create_user(username, password)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": "Signup successful!", "username": username}), 200

# Login route to authenticate user
@app.route('/api/login', methods=['POST'])
def login():
    data = request.form
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    if authenticate_user(username, password):
        session['user'] = username
        return jsonify({"message": "Login successful!"}), 200
    return jsonify({"error": "Invalid credentials."}), 401

# Keep the rest of the original dashboard.py content unchanged ...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    try:
        import run as _test_mgr
        print(f"  5 run.py loaded from: {MANAGER_DIR}")
    except ImportError as e:
        print(f"\n  2 ERROR: Cannot import run.py")
        print(f"     Looking in: {MANAGER_DIR}")
        print(f"     Reason: {e}")
        print(f"     Fix: make sure agents/manager/run.py exists\n")

    print(f"\n{'='*50}")
    print(f"  NexusSynapse Dashboard  7b  http://localhost:{port}")
    print(f"  Manager dir : {MANAGER_DIR}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
