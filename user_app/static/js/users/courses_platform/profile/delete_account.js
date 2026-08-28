document.addEventListener('DOMContentLoaded', () => {
    const openBtn = document.getElementById('openDeleteAccountBtn');
    const modalEl = document.getElementById('deleteAccountModal');
    if (!openBtn || !modalEl) return;

    const modal = new bootstrap.Modal(modalEl);
    const stepWarn = document.getElementById('deleteStepWarn');
    const stepOtp = document.getElementById('deleteStepOtp');
    const ack = document.getElementById('deleteAcknowledge');
    const nextBtn = document.getElementById('deleteNextBtn');
    const finalBtn = document.getElementById('deleteFinalBtn');
    const cancelBtn = document.getElementById('deleteCancelBtn');
    const otpInput = document.getElementById('deleteOtpInput');
    const confirmText = document.getElementById('deleteConfirmText');
    const warnMsg = document.getElementById('deleteWarnMsg');
    const otpMsg = document.getElementById('deleteOtpMsg');
    const sentTo = document.getElementById('deleteSentTo');
    const resendBtn = document.getElementById('deleteResendBtn');

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

    let busy = false;

    function say(el, text, kind) {
        if (!el) return;
        el.className = 'small mt-2 fw-bold ' + (kind === 'error' ? 'text-danger' : 'text-success');
        el.textContent = text;
    }

    function post(url, payload) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(payload)
        }).then(async (res) => ({ ok: res.ok, data: await res.json().catch(() => ({})) }));
    }

    function setCount(id, value) {
        const el = document.getElementById(id);
        if (el && value > 0) el.textContent = value;
    }

    openBtn.addEventListener('click', async () => {
        stepWarn.style.display = '';
        stepOtp.style.display = 'none';
        nextBtn.style.display = '';
        finalBtn.style.display = 'none';
        nextBtn.disabled = true;
        ack.checked = false;
        otpInput.value = '';
        confirmText.value = '';
        warnMsg.textContent = '';
        otpMsg.textContent = '';
        modal.show();

        try {
            const res = await fetch('/api/profile/delete/summary');
            const data = await res.json();
            if (data.status === 'success') {
                setCount('lossEnrollments', data.summary.enrollments);
                setCount('lossPurchases', data.summary.purchases);
                setCount('lossAttempts', data.summary.test_attempts);
            }
        } catch (e) {
            console.error('summary error', e);
        }
    });

    ack.addEventListener('change', () => {
        nextBtn.disabled = !ack.checked;
    });

    async function requestOtp(button, msgEl) {
        if (busy) return;
        busy = true;
        const original = button.textContent;
        button.disabled = true;
        button.textContent = 'Sending code...';

        const { ok, data } = await post('/api/profile/delete/send-otp', { acknowledge: true });

        button.textContent = original;
        button.disabled = false;
        busy = false;

        if (!ok || data.status !== 'success') {
            say(msgEl, data.message || 'Could not send the code. Please try again.', 'error');
            return false;
        }

        if (sentTo) sentTo.textContent = data.sent_to || '';
        say(msgEl, data.message || 'Code sent.', 'success');
        return true;
    }

    nextBtn.addEventListener('click', async () => {
        if (!ack.checked) {
            say(warnMsg, 'Please tick the confirmation box first.', 'error');
            return;
        }
        const sent = await requestOtp(nextBtn, warnMsg);
        if (!sent) return;

        stepWarn.style.display = 'none';
        stepOtp.style.display = '';
        nextBtn.style.display = 'none';
        finalBtn.style.display = '';
        otpMsg.textContent = '';
        otpInput.focus();
    });

    resendBtn.addEventListener('click', () => requestOtp(resendBtn, otpMsg));

    otpInput.addEventListener('input', () => {
        otpInput.value = otpInput.value.replace(/\D/g, '').slice(0, 6);
    });

    confirmText.addEventListener('input', () => {
        confirmText.value = confirmText.value.toUpperCase();
    });

    finalBtn.addEventListener('click', async () => {
        if (busy) return;

        const otp = otpInput.value.trim();
        const text = confirmText.value.trim().toUpperCase();

        if (otp.length !== 6) {
            say(otpMsg, 'Enter the 6-digit code from your email.', 'error');
            return;
        }
        if (text !== 'DELETE') {
            say(otpMsg, 'Type DELETE exactly to confirm.', 'error');
            return;
        }

        busy = true;
        finalBtn.disabled = true;
        cancelBtn.disabled = true;
        finalBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Deleting...';

        const { ok, data } = await post('/api/profile/delete/confirm', {
            acknowledge: true,
            otp: otp,
            confirm_text: text
        });

        if (ok && data.status === 'success') {
            say(otpMsg, data.message || 'Account deleted.', 'success');
            window.location.href = data.redirect_url || '/';
            return;
        }

        busy = false;
        finalBtn.disabled = false;
        cancelBtn.disabled = false;
        finalBtn.innerHTML = '<i class="fas fa-user-slash me-1"></i> Permanently delete';
        say(otpMsg, data.message || 'Could not delete the account. Please try again.', 'error');
    });
});
