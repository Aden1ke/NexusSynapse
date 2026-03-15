from flask import Flask, request, redirect, url_for, flash, render_template
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Use a secure method to store this

# Dummy data for example purposes
dummy_users = {
    'user1': 'pbkdf2:sha256:150000$8szj4X3P$9f82afa4734f9d021a80369b2419bff57dab3f5978e44b1853cd8e6f925d7154',  # password is 'password1'
}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if user exists and verify password
        if username in dummy_users and check_password_hash(dummy_users[username], password):
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))  # Redirect on success
        else:
            flash('Invalid username or password', 'error')  # Error message on failure
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # Placeholder for actual dashboard logic
    return "Welcome to your dashboard!"

if __name__ == '__main__':
    app.run(debug=True)