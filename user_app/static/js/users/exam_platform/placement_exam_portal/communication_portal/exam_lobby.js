const socket = io();
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

  // Full screen is entered on the Start click itself (a real user gesture),
  // and navigation waits until it is active so the test window opens in full
  // screen; the window guard on that page silently re-enters if the browser
  // dropped it across the navigation. No popup is involved at entry.
  const startLink = document.getElementById('startLink');
  if (startLink) {
    let launching = false;
    startLink.addEventListener('click', function (e) {
      e.preventDefault();
      if (btnStart.disabled || launching) return;
      launching = true;
      btnStart.disabled = true;
      btnStart.innerText = 'Starting...';
      const href = startLink.getAttribute('href');
      let done = false;
      function go() {
        if (done) return;
        done = true;
        window.location.href = href;
      }
      const el = document.documentElement;
      const fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
      if (fn) {
        try {
          const r = fn.call(el);
          if (r && typeof r.then === 'function') { r.then(go).catch(go); }
          else { go(); }
        } catch (err) { go(); }
      } else { go(); }
      setTimeout(go, 600);
    });
  }
