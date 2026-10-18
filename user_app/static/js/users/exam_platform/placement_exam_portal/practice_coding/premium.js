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

    var AUTO_HIDE_MS = 5000;
    var failTimer = null;
    var modalErrTimer = null;

    function fail(message) {
        if (!errorBox) { alert(message); return; }
        if (failTimer) clearTimeout(failTimer);
        errorBox.textContent = message;
        errorBox.classList.remove('is-hidden', 'is-leaving');
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
        failTimer = setTimeout(function () {
            errorBox.classList.add('is-leaving');
            failTimer = setTimeout(function () { errorBox.classList.add('is-hidden'); errorBox.classList.remove('is-leaving'); }, 350);
        }, AUTO_HIDE_MS);
    }

    function showModalError(message) {
        if (!modalErr) { alert(message); return; }
        if (modalErrTimer) clearTimeout(modalErrTimer);
        modalErr.textContent = message;
        modalErr.classList.remove('is-hidden', 'is-leaving');
        modalErrTimer = setTimeout(function () {
            modalErr.classList.add('is-leaving');
            modalErrTimer = setTimeout(function () { modalErr.classList.add('is-hidden'); modalErr.classList.remove('is-leaving'); }, 350);
        }, AUTO_HIDE_MS);
    }

    function clearModalError() {
        if (modalErrTimer) { clearTimeout(modalErrTimer); modalErrTimer = null; }
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

    function planData() {
        var d = (activeButton && activeButton.dataset) || {};
        var info = (CFG.plans || {})[plan] || {};
        var paise = Number(info.paise) || 0;
        var price = d.price ? Number(d.price) * 100 : 0;
        var monthly = Number(((CFG.plans || {}).monthly || {}).paise) || 0;
        var original = price || (plan === 'yearly' && monthly ? monthly * 12 : paise);
        return { info: info, paise: paise, original: original, discount: Math.max(0, original - paise),
                 days: Number(d.days) || (plan === 'yearly' ? 365 : 30), label: d.label || info.label || plan,
                 off: d.discount ? Number(d.discount) : 0 };
    }

    function renderTicket() {
        var pd = planData();
        function set(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }
        function show(id, on) { var el = document.getElementById(id); if (el) el.classList.toggle('is-hidden', !on); }
        set('pmTkPlan', pd.label + ' plan');
        set('pmTkNow', rupees(pd.paise));
        set('pmTkWas', rupees(pd.original)); show('pmTkWas', pd.discount > 0);
        set('pmTkOff', (pd.off ? pd.off + '% off' : 'save ' + rupees(pd.discount))); show('pmTkOff', pd.discount > 0);
        var days = document.querySelector('#pmTkDays span');
        var until = (activeButton && activeButton.dataset && activeButton.dataset.until) || '';
        if (days) days.textContent = until ? 'Access until ' + until + ' (' + pd.days + ' days)' : 'Valid for ' + pd.days + ' days from today';
    }

    function renderSummary() {
        var pd = planData();
        var info = pd.info;
        var paise = pd.paise;
        var original = pd.original;
        var discount = pd.discount;

        function set(id, text) {
            var el = document.getElementById(id);
            if (el) el.textContent = text;
        }
        var untilText = (activeButton && activeButton.dataset && activeButton.dataset.until) || '';
        set('pmSumPlan', pd.label + (untilText ? ' (until ' + untilText + ')' : ' (' + pd.days + ' days)'));
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
        var title = document.getElementById('pmStepTitle');
        if (title) title.textContent = step === 1 ? 'Your phone number' : 'Confirm your order';
        var rail = document.getElementById('pmRail');
        if (rail) rail.style.width = (step === 1 ? 33 : 66) + '%';
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
        if (planLine) planLine.textContent = 'Checkout';
        renderTicket();
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
                        window.location.replace(CFG.nextUrl || v.data.redirect || window.location.href);
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
            phone: value('pmPhone'),
            course_code: CFG.courseCode || ''
        }).then(function (r) {
            if (!r.ok) {
                showModalError(r.data.error || 'Could not start the payment. Please try again.');
                render();
                return;
            }
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

    (function () {
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        document.querySelectorAll('.pm-price__amount[data-count]').forEach(function (el, i) {
            var target = Number(el.getAttribute('data-count')) || 0;
            var start = null;
            var duration = 650;
            function tick(ts) {
                if (start === null) start = ts;
                var t = Math.min(1, (ts - start) / duration);
                var eased = 1 - Math.pow(1 - t, 3);
                el.textContent = '\u20B9' + Math.round(target * eased);
                if (t < 1) requestAnimationFrame(tick); else el.classList.add('is-counting');
            }
            setTimeout(function () { requestAnimationFrame(tick); }, 150 + i * 120);
        });
    })();

    (function () {
        var targets = document.querySelectorAll('.pm-what, .pm-section, .pm-faq');
        if (!targets.length || !('IntersectionObserver' in window)) return;
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); }
            });
        }, { threshold: 0, rootMargin: '0px 0px -8% 0px' });
        targets.forEach(function (el) { el.classList.add('pm-reveal'); io.observe(el); });
    })();

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
