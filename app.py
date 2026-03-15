from flask import Flask, render_template, request, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            return "Invalid input", 400
        hashed_password = generate_password_hash(password)
        # Store username and hashed_password to the database
        return redirect(url_for('welcome'))
    return render_template('signup.html')

@app.route('/welcome')
def welcome():
    return "Welcome to the platform!"

if __name__ == '__main__':
    app.run(debug=True)
