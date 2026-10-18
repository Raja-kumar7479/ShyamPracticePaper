(function () {
const socket = io({ transports: ['websocket', 'polling'] });
  const statusDot = document.getElementById('socketStatus');
  const statusMsg = document.getElementById('socketMsg');

  socket.on('connect', () => {
      statusDot.classList.add('online');
      statusMsg.textContent = "Secure Connection Established";
      socket.emit('join_exam', { session_id: document.getElementById('lobbyTestKey').value });
  });

  socket.on('disconnect', () => {
      statusDot.classList.remove('online');
      statusMsg.textContent = "Connection Lost - Reconnecting...";
  });

  let seconds = 10;
  const topTimer = document.getElementById('topTimer');
  const btnTimerText = document.getElementById('btnTimerText');
  const btnStart = document.getElementById('btnStart');

  const interval = setInterval(() => {
    seconds--;
    topTimer.textContent = `Ready to start? ${seconds}s`;
    btnTimerText.textContent = `Start in ${seconds}s`;
    if(seconds <= 0){
      clearInterval(interval);
      topTimer.textContent = "Good Luck!";
      btnTimerText.style.display = 'none';
      btnStart.disabled = false;
      btnStart.innerText = "Start Test";
    }
  }, 1000);
  const startLink = document.getElementById('startLink');
  if (startLink) {
    let launching = false;
    startLink.addEventListener('click', function (e) {
      e.preventDefault();
      if (btnStart.disabled || launching) return;
      var consent = document.getElementById('consentCheck');
      if (consent && !consent.checked) {
        consent.focus();
        document.getElementById('consentWrap').classList.add('is-missing');
        return;
      }
      launching = true;
      btnStart.disabled = true;
      btnStart.innerText = 'Starting...';
      const href = startLink.getAttribute('href');
      if (typeof window.sppLaunchExam === 'function') {
        window.sppLaunchExam({ url: href, expect: '/start_test_window/' });
      } else {
        window.location.href = href;
      }
    });
  }
}());
