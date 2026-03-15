from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# In-memory user storage for demonstration. Replace with a database in production
users = {}

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Missing fields'}), 400

    if username in users:
        return jsonify({'error': 'User already exists'}), 400

    # Hash the password for security
    hashed_password = generate_password_hash(password)
    users[username] = {'email': email, 'password': hashed_password}
    
    return jsonify({'message': 'User created successfully'}), 201

# To run the Flask app (for demonstration purposes)
if __name__ == '__main__':
    app.run(debug=True)