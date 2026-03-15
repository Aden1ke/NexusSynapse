from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # should be placed in environment variables

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
            flash('Database error: ""{}'.format(e), 'danger')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))

        flash('Incorrect email or password', 'danger')

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)