/* Premium checkout: collect the phone, confirm the billing summary, order
 * from our server, pay in Razorpay's window, then verify on our server. The
 * server-side signature check is what actually grants premium - this file
 * only drives the flow.
 *
 * The details step sits in front of the gateway on purpose. Opening Razorpay
 * with no contact prefilled let it fill that field from whatever it had
 * remembered in the browser, so buyers saw a phone number that was not theirs. */
(function () {
    'use strict';

    var CFG = window.PCP_BILLING || {};
    var errorBox = document.getElementById('pmError');
    var modal = document.getElementById('pmModal');
    var form = document.getElementById('pmForm');
    var modalErr = document.getElementById('pmModalErr');
    var planLine = document.getElementById('pmPlanLine');
    var nextBtn = document.getElementById('pmNext');
    var backBtn = document.getElementById('pmBack');
    var closeBtn = document.getElementById('pmClose');
    var steps = form ? form.querySelectorAll('.pm-step') : [];
    var dots = modal ? modal.querySelectorAll('[data-step-dot]') : [];

    var LAST_STEP = 2;
    var step = 1;
    var plan = null;
    var activeButton = null;

    function fail(message) {
        if (!errorBox) { alert(message); return; }
        errorBox.textContent = message;
        errorBox.classList.remove('is-hidden');
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function showModalError(message) {
        if (!modalErr) { alert(message); return; }
        modalErr.textContent = message;
        modalErr.classList.remove('is-hidden');
    }

    function clearModalError() {
        if (modalErr) modalErr.classList.add('is-hidden');
    }

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
            },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) { return { ok: res.ok, data: data }; });
        });
    }

    function value(id) {
        var el = document.getElementById(id);
        return el ? el.value.trim() : '';
    }

    function digitsOnly(el, max) {
        if (!el) return;
        el.addEventListener('input', function () {
            var cleaned = el.value.replace(/\D/g, '').slice(0, max);
            if (cleaned !== el.value) el.value = cleaned;
        });
    }
    digitsOnly(document.getElementById('pmPhone'), 10);

    /* Mirrors _clean_phone() on the server. The server is the authority; this
     * only saves the buyer a round trip. */
    function stepError(which) {
        if (which === 1 && !/^[1-9]\d{9}$/.test(value('pmPhone'))) {
            return 'Enter a valid 10-digit phone number starting from 1-9.';
        }
        return null;
    }

    function rupees(paise) {
        var whole = paise / 100;
        return '₹' + (whole % 1 === 0 ? String(whole) : whole.toFixed(2));
    }

    /* The billing summary: plan, price, and for the yearly plan the saving vs
     * paying month by month, shown as a discount off the 12-month price. */
    function renderSummary() {
        var info = (CFG.plans || {})[plan] || {};
        var paise = Number(info.paise) || 0;
        var monthly = Number(((CFG.plans || {}).monthly || {}).paise) || 0;
        var original = plan === 'yearly' && monthly ? monthly * 12 : paise;
        var discount = original - paise;

        function set(id, text) {
            var el = document.getElementById(id);
            if (el) el.textContent = text;
        }
        set('pmSumPlan', (info.label || plan) + (plan === 'yearly' ? ' (12 months)' : ' (30 days)'));
        set('pmSumPhone', '+91 ' + value('pmPhone'));
        set('pmSumPrice', rupees(original));
        set('pmSumTotal', rupees(paise));
        var row = document.getElementById('pmSumDiscountRow');
        if (row) {
            row.classList.toggle('is-hidden', discount <= 0);
            if (discount > 0) set('pmSumDiscount', '- ' + rupees(discount));
        }
    }

    function render() {
        Array.prototype.forEach.call(steps, function (el) {
            el.classList.toggle('is-hidden', Number(el.getAttribute('data-step')) !== step);
        });
        Array.prototype.forEach.call(dots, function (el) {
            var n = Number(el.getAttribute('data-step-dot'));
            el.classList.toggle('is-active', n === step);
            el.classList.toggle('is-done', n < step);
        });
        if (backBtn) backBtn.classList.toggle('is-hidden', step === 1);
        if (nextBtn) {
            nextBtn.textContent = step === LAST_STEP ? 'Proceed to Pay' : 'Next';
            nextBtn.disabled = false;
        }
        if (step === LAST_STEP) renderSummary();
        var current = form.querySelector('.pm-step[data-step="' + step + '"] input');
        if (current) current.focus();
    }

    function openModal(planKey, button) {
        plan = planKey;
        activeButton = button;
        step = 1;
        clearModalError();
        if (errorBox) errorBox.classList.add('is-hidden');
        if (planLine) {
            var info = (CFG.plans || {})[planKey] || {};
            planLine.textContent = (info.label || planKey) + ' plan';
            if (info.paise) planLine.textContent += ' - ' + rupees(Number(info.paise));
        }
        modal.classList.remove('is-hidden');
        document.body.classList.add('pm-noscroll');
        render();
    }

    function closeModal() {
        modal.classList.add('is-hidden');
        document.body.classList.remove('pm-noscroll');
        if (activeButton) activeButton.disabled = false;
        activeButton = null;
    }

    function openCheckout(order) {
        window.sppCheckout.open({
            key: order.key_id,
            amount: order.amount,
            currency: order.currency,
            description: 'Coding Practice Premium (' + order.plan + ')',
            orderId: order.order_id,
            name: order.username || CFG.username,
            email: order.email || CFG.email,
            contact: order.contact || value('pmPhone'),
            onSuccess: function (resp) {
                post(CFG.verifyUrl, resp).then(function (v) {
                    if (v.ok && v.data.success) {
                        window.location.replace(v.data.redirect || window.location.href);
                    } else {
                        fail(v.data.error ||
                             'Payment received but verification failed. Contact support with your payment ID.');
                    }
                }).catch(function () {
                    fail('Payment made, but we could not confirm it. Refresh this page - ' +
                         'if premium is still off, contact support with your payment ID.');
                });
            },
            onDismiss: function () {
                if (activeButton) activeButton.disabled = false;
            },
            onFailed: function (resp) {
                fail('Payment failed: ' + ((resp.error && resp.error.description) || 'try again.'));
                if (activeButton) activeButton.disabled = false;
            }
        });
    }

    function submitOrder() {
        nextBtn.disabled = true;
        nextBtn.textContent = 'Starting…';

        post(CFG.orderUrl, {
            plan: plan,
            phone: value('pmPhone')
        }).then(function (r) {
            if (!r.ok) {
                showModalError(r.data.error || 'Could not start the payment. Please try again.');
                render();
                return;
            }
            /* The gateway replaces this dialog, so it closes before opening -
             * otherwise dismissing Razorpay leaves the form stacked behind it. */
            modal.classList.add('is-hidden');
            document.body.classList.remove('pm-noscroll');
            openCheckout(r.data);
        }).catch(function () {
            showModalError('Network error. Please try again.');
            render();
        });
    }

    if (form) {
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            clearModalError();
            var problem = stepError(step);
            if (problem) { showModalError(problem); return; }
            if (step < LAST_STEP) { step += 1; render(); return; }
            submitOrder();
        });
    }

    if (backBtn) {
        backBtn.addEventListener('click', function () {
            clearModalError();
            if (step > 1) { step -= 1; render(); }
        });
    }

    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) closeModal();
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && !modal.classList.contains('is-hidden')) closeModal();
        });
    }

    document.querySelectorAll('.pm-subscribe').forEach(function (button) {
        button.addEventListener('click', function () {
            button.disabled = true;
            if (!modal || !form) {
                fail('Checkout is unavailable on this page. Please refresh and try again.');
                button.disabled = false;
                return;
            }
            openModal(button.getAttribute('data-plan'), button);
        });
    });
}());
