const form = document.getElementById('auth-form');
const smsCodeContainer = document.getElementById('sms-code-container');
const registerContainer = document.getElementById('register-container');
const notification = document.getElementById('notification');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const phone = document.getElementById('phone').value;

  const res = await fetch('/auth/send-sms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  });

  if (res.status === 404) {
    registerContainer.style.display = 'block';
  } else if (res.status === 200) {
    const { otp } = await res.json();
    smsCodeContainer.style.display = 'block';
    notify(`Код: ${otp}`);
  }
});

async function verifySMS() {
  const phone = document.getElementById('phone').value;
  const otp = document.getElementById('sms-code').value;

  const res = await fetch('/auth/verify-sms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, otp }),
  });

  if (res.ok) {
    window.location.href = '/static/dashboard.html';
  } else {
    notify('Неверный код');
  }
}

async function registerUser() {
  const phone = document.getElementById('phone').value;
  const name = document.getElementById('name').value;
  const email = document.getElementById('email').value;

  const res = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, name, email }),
  });

  if (res.ok) {
    const { otp } = await res.json();
    smsCodeContainer.style.display = 'block';
    notify(`Код: ${otp}`);
  }
}

function notify(message) {
  notification.innerText = message;
  notification.style.display = 'block';
  setTimeout(() => (notification.style.display = 'none'), 5000);
}
