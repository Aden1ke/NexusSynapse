import unittest
from werkzeug.security import check_password_hash
from app import app, db, User

class FlaskTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_users.db'
        self.app = app.test_client()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    def test_signup_page_loads(self):
        # Ensure the signup page loads correctly
        response = self.app.get('/signup')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign Up', response.data)

    def test_signup_functionality(self):
        # Ensure a user can signup
        response = self.app.post('/signup', data=dict(
            username='new_user', email='new_user@example.com', password='Newuser123!'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Signup successful!', response.data)

        # Password should be hashed
        user = User.query.filter_by(username='new_user').first()
        self.assertIsNotNone(user)
        self.assertTrue(check_password_hash(user.password, 'Newuser123!'))

    def test_signup_existing_user(self):
        # Ensure the signup process checks for existing user
        self.app.post('/signup', data=dict(
            username='existing_user', email='existing_user@example.com', password='Existing123!'
        ), follow_redirects=True)
        response = self.app.post('/signup', data=dict(
            username='existing_user', email='existing_user@example.com', password='Existing123!'
        ), follow_redirects=True)
        self.assertIn(b'Email address already in use.', response.data)


if __name__ == '__main__':
    unittest.main()
