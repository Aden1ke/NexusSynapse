// Basic form handling for the login page.
document.querySelector('.login-form').addEventListener('submit', function(event) {
    event.preventDefault();

    const username = document.querySelector('#username').value;
    const password = document.querySelector('#password').value;

    if(!username || !password) {
        alert('Please fill in both fields.');
        return;
    }

    // Placeholder for further authentication processes.
    alert('Successfully submitted!');
});