// Basic form handling for the signup page.
document.querySelector('.signup-form').addEventListener('submit', function(event) {
    event.preventDefault();

    const email = document.querySelector('#email').value;
    const username = document.querySelector('#username').value;
    const password = document.querySelector('#password').value;
    const confirmPassword = document.querySelector('#confirm-password').value;

    if(!email || !username || !password || !confirmPassword) {
        alert('Please fill in all fields.');
        return;
    }

    if (password !== confirmPassword) {
        alert('Passwords do not match.');
        return;
    }

    // Placeholder for further registration processes.
    alert('Successfully signed up!');
});