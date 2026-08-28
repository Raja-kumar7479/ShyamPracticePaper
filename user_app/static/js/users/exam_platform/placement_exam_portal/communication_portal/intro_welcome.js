(function () {
    const smartBtn = document.getElementById('smartBtn');
    const permBadge = document.getElementById('permBadge');
    const permText = document.getElementById('permText');
    const proceedBtn = document.getElementById('proceedBtn');
    const btnProceedReal = document.getElementById('btnProceedReal');
    const step3 = document.getElementById('step3');
    const iconPerms = document.getElementById('iconPerms');

    if (!smartBtn || !btnProceedReal) return;

    const iwData = document.getElementById('iwData');
    const confirmUrl = iwData ? iwData.dataset.confirmUrl : '';

    let mediaGranted = false;
    let screenGranted = false;

    function reportPermissions() {
        if (!confirmUrl) return Promise.resolve();
        return fetch(confirmUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                camera: mediaGranted,
                microphone: mediaGranted,
                screen: screenGranted
            })
        }).catch(function () {});
    }

    function notify(message, kind) {
        let stack = document.querySelector('.iw-toasts');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'iw-toasts';
            document.body.appendChild(stack);
        }
        const box = document.createElement('div');
        box.className = 'iw-toast' + (kind === 'error' ? ' iw-toast--error' : '');
        box.setAttribute('role', 'alert');
        const icon = document.createElement('i');
        icon.className = kind === 'error' ? 'bi bi-exclamation-triangle-fill' : 'bi bi-info-circle-fill';
        const text = document.createElement('span');
        text.textContent = message;
        box.appendChild(icon);
        box.appendChild(text);
        stack.appendChild(box);
        setTimeout(function () { box.remove(); }, 5000);
    }

    function lockProceed(reason) {
        btnProceedReal.disabled = true;
        if (proceedBtn) {
            proceedBtn.style.pointerEvents = 'none';
            proceedBtn.setAttribute('aria-disabled', 'true');
        }
        if (step3) step3.classList.remove('active');
        if (permBadge) {
            permBadge.className = 'badge pending';
            permBadge.textContent = '2';
        }
        if (iconPerms) {
            iconPerms.classList.remove('success');
            iconPerms.classList.add('active');
        }
        if (permText) {
            permText.classList.remove('text-success', 'fw-bold');
            permText.innerText = reason;
        }
        smartBtn.classList.remove('is-hidden', 'btn-green');
        smartBtn.disabled = false;
        smartBtn.innerHTML = '<i class="bi bi-camera-video"></i> Check Camera';
        mediaGranted = false;
        screenGranted = false;
        reportPermissions();
    }

    function unlockProceed() {
        if (!mediaGranted || !screenGranted) return;
        if (permBadge) {
            permBadge.className = 'badge done';
            permBadge.innerHTML = '<i class="bi bi-check"></i>';
        }
        if (permText) {
            permText.innerText = 'All permissions granted.';
            permText.classList.add('text-success', 'fw-bold');
        }
        if (iconPerms) {
            iconPerms.classList.remove('active');
            iconPerms.classList.add('success');
        }
        smartBtn.classList.add('is-hidden');
        if (step3) step3.classList.add('active');
        if (proceedBtn) {
            proceedBtn.style.pointerEvents = 'auto';
            proceedBtn.removeAttribute('aria-disabled');
        }
        btnProceedReal.disabled = false;
    }

    function watchTrack(track, reason) {
        track.addEventListener('ended', function () {
            lockProceed(reason);
            notify(reason, 'error');
        });
    }

    smartBtn.addEventListener('click', async () => {
        if (!mediaGranted) {
            try {
                smartBtn.disabled = true;
                smartBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Checking...';
                const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
                window.localStream = stream;

                const hasVideo = stream.getVideoTracks().length > 0;
                const hasAudio = stream.getAudioTracks().length > 0;
                if (!hasVideo || !hasAudio) {
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    throw new Error('Both camera and microphone are required.');
                }

                stream.getTracks().forEach(function (t) {
                    watchTrack(t, 'Camera or microphone was turned off. Grant access again to continue.');
                });

                mediaGranted = true;
                permText.innerText = 'Camera & Mic connected. Now share your screen.';
                smartBtn.disabled = false;
                smartBtn.innerHTML = '<i class="bi bi-display"></i> Start Screen Capture';
                smartBtn.classList.add('btn-green');
            } catch (err) {
                console.error(err);
                notify('Camera and microphone access is required to start this test.', 'error');
                smartBtn.disabled = false;
                smartBtn.innerHTML = '<i class="bi bi-camera-video"></i> Retry Camera';
            }
        } else {
            try {
                smartBtn.disabled = true;
                const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
                window.screenStream = screenStream;

                const videoTrack = screenStream.getVideoTracks()[0];
                if (!videoTrack) {
                    throw new Error('No screen track returned.');
                }

                const settings = typeof videoTrack.getSettings === 'function' ? videoTrack.getSettings() : {};
                if (settings.displaySurface && settings.displaySurface !== 'monitor') {
                    screenStream.getTracks().forEach(function (t) { t.stop(); });
                    smartBtn.disabled = false;
                    notify('You must share your entire screen, not a single window or tab.', 'error');
                    return;
                }

                watchTrack(videoTrack, 'Screen sharing stopped. Share your screen again to continue.');

                screenGranted = true;
                smartBtn.disabled = false;
                await reportPermissions();
                unlockProceed();
            } catch (err) {
                console.error(err);
                smartBtn.disabled = false;
                notify('Screen sharing is required to start this test.', 'error');
            }
        }
    });

    if (proceedBtn) {
        proceedBtn.addEventListener('click', function (e) {
            if (!mediaGranted || !screenGranted) {
                e.preventDefault();
                notify('Grant camera, microphone and screen access before proceeding.', 'error');
                return;
            }
            const live = window.localStream && window.localStream.getTracks().some(function (t) {
                return t.readyState === 'live';
            });
            const screenLive = window.screenStream && window.screenStream.getVideoTracks().some(function (t) {
                return t.readyState === 'live';
            });
            if (!live || !screenLive) {
                e.preventDefault();
                lockProceed('Permissions were lost. Grant access again to continue.');
                notify('Permissions were lost. Grant access again to continue.', 'error');
            }
        });
    }

    lockProceed('We need access to your Camera, Microphone, and Screen.');
})();
