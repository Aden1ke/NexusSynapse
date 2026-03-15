from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Implement basic authentication logic
        username = request.form.get('username')
        password = request.form.get('password')
        # Here, you might want to check actual user credentials.
        if username == "admin" and password == "password":
            return redirect(url_for('welcome'))
        else:
            return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Here you would handle form submission and user creation logic
        username = request.form.get('username')
        password = request.form.get('password')
        # Add user creation logic
        return redirect(url_for('welcome'))
    return render_template('signup.html')

@app.route('/welcome')
def welcome():
    return "Welcome to the platform!"

if __name__ == '__main__':
    app.run(debug=True)
