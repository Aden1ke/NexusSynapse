from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # should be placed in environment variables

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

        # TODO: Store the user credentials in the database

        flash('Account created successfully!', 'success')
        return redirect(url_for('signup'))

    return render_template('signup.html')

if __name__ == '__main__':
    app.run(debug=True)