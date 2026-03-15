from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Ideally should be set from environment variables

login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, username, email, password):
        self.id = id
        self.username = username
        self.email = email
        self.password = password

    def get_id(self):
        return self.id

    @staticmethod
    def get_user_by_email(email):
        conn = get_db_connection()
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if user_row:
            return User(user_row['id'], user_row['username'], user_row['email'], user_row['password'])
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    conn.close()
    if user_row:
        return User(user_row['id'], user_row['username'], user_row['email'], user_row['password'])
    return None

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Input validation
        if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash('Invalid email address!', 'danger')
            return redirect(url_for('signup'))

        if len(password) < 8:
            flash('Password must be at least 8 characters long!', 'danger')
            return redirect(url_for('signup'))

        # Password hashing
        hashed_password = generate_password_hash(password, method='sha256')

        # Store the user credentials in the database
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                         (username, email, hashed_password))
            conn.commit()
            conn.close()
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
        except sqlite3.Error as e:
            flash(f'Database error: "{e}"', 'danger')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.get_user_by_email(email)

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))

        flash('Incorrect email or password', 'danger')

    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)