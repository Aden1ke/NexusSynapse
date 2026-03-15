from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = 'supersecretkey'
login_manager = LoginManager()
login_manager.init_app(app)

# In-memory user storage for demonstration (use a database in production)
users = {}

class User(UserMixin):
    def __init__(self, id, username, email, password):
        self.id = id
        self.username = username
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if username in users:
            flash('Username already exists!', 'error')
            return redirect(url_for('signup'))

        # Create a new user
        user_id = len(users) + 1
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(id=user_id, username=username, email=email, password=hashed_password)
        users[username] = new_user

        login_user(new_user)
        flash('Signup successful!', 'success')
        return redirect(url_for('dashboard'))  # Redirect to dashboard or desired page

    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    return "Welcome to the dashboard!"  # Placeholder for the dashboard page

if __name__ == '__main__':
    app.run(debug=True)