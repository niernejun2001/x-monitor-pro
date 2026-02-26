document.addEventListener('DOMContentLoaded', () => {
  const jumpBtn = document.getElementById('jumpBtn');
  const usernameInput = document.getElementById('username');
  const statusDiv = document.getElementById('status');

  // Focus input on load
  usernameInput.focus();

  // Handle click
  jumpBtn.addEventListener('click', () => {
    jump();
  });

  // Handle Enter key
  usernameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      jump();
    }
  });

  function jump() {
    const username = usernameInput.value.trim().replace('@', '');
    if (!username) {
      statusDiv.textContent = 'Please enter a username';
      return;
    }

    const url = `https://twitter.com/${username}/with_replies`;
    chrome.tabs.create({ url: url });
  }
});
