document.addEventListener('DOMContentLoaded', function () {

    const $ = (id) => document.getElementById(id);
    const log = (m, x) => console.log('[PURCHASES] ' + m, x === undefined ? '' : x);
    const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    const navItems = document.querySelectorAll('.as-view[data-view]');
    const views = { lookup: $('puView-lookup'), attention: $('puView-attention'), payment: $('puView-payment') };

    let currentEmail = '';
    let lastData = null;
    let liveMap = {};
    let searchTimer = null;
    let searchSeq = 0;

    function esc(v) {
        return String(v === null || v === undefined ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    const money = (v) => 'Rs. ' + Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function showView(name) {
        navItems.forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
        Object.keys(views).forEach(k => views[k] && views[k].classList.toggle('is-active', k === name));
        if (window.matchMedia('(max-width: 991px)').matches && window.asClose) window.asClose();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        if (name === 'attention' && !$('puAttentionList').innerHTML) scanAttention();
    }
    navItems.forEach(b => b.addEventListener('click', () => showView(b.dataset.view)));

    function say(el, text, kind) {
        if (typeof window.adminToast === 'function') { window.adminToast(text, kind === 'success' ? 'success' : 'danger'); return; }
        el.className = 'alert mt-3 alert-' + (kind || 'danger');
        el.textContent = text;
        el.classList.remove('is-hidden');
        setTimeout(() => el.classList.add('is-hidden'), 6000);
    }

    function statusChip(status) {
        const s = String(status || '').toLowerCase();
        let cls = 'secondary';
        if (['paid', 'success', 'captured', 'free', 'active', 'granted'].includes(s)) cls = 'success';
        else if (['pending', 'authorized', 'created', 'unreachable'].includes(s)) cls = 'warning';
        else if (['failed', 'cancelled', 'expired', 'refunded', 'revoked', 'mismatch', 'not_granted'].includes(s)) cls = 'danger';
        return `<span class="badge bg-${cls}">${esc(String(status || '-').replace('_', ' '))}</span>`;
    }

    function accessChip(access) {
        const map = { granted: ['success', 'Granted'], expired: ['secondary', 'Expired'], revoked: ['danger', 'Revoked'], not_granted: ['danger', 'Not granted'] };
        const m = map[access] || ['secondary', access || '-'];
        return `<span class="badge bg-${m[0]}">${esc(m[1])}</span>`;
    }

    function gatewayCell(key) {
        const info = liveMap[key];
        if (!key) return '<span class="pu-nolive" title="Free or internal entry - no gateway payment">-</span>';
        if (!info) return `<span class="pu-live-wait" data-live-for="${esc(key)}"><span class="spinner-border spinner-border-sm"></span></span>`;
        let text = info.status || '-';
        if (info.refund_status === 'full') text = 'refunded';
        if (info.refund_status === 'partial') text = 'partly refunded';
        return `${statusChip(text)}${info.amount ? `<br><small class="text-muted">${money(info.amount)}${info.method ? ' · ' + esc(info.method) : ''}</small>` : ''}`;
    }

    function verdictCell(key, fallbackAccess, kind) {
        const info = liveMap[key];
        if (!key) return '<small class="text-muted">internal entry</small>';
        if (!info) return '<small class="text-muted">checking...</small>';
        const v = info.verdict || {};
        let html = `<span class="pu-verdict pu-verdict--${esc(v.kind || 'secondary')}">${esc(v.text || '-')}</span>`;
        if (v.action === 'grant') {
            const orderId = info.order_id || key;
            html += ` <button type="button" class="btn btn-warning btn-sm pu-grant" data-order="${esc(orderId)}"><i class="fas fa-unlock"></i> Grant access</button>`;
        } else if (v.action === 'revoke') {
            const pid = info.payment_id || key;
            html += ` <button type="button" class="btn btn-danger btn-sm pu-revoke" data-pid="${esc(pid)}"><i class="fas fa-ban"></i> Revoke</button>`;
        }
        return html;
    }

    function copyBtn(value) {
        if (!value) return '';
        return `<button type="button" class="pu-copy" data-copy="${esc(value)}" title="Copy"><i class="fas fa-copy"></i></button>`;
    }

    document.addEventListener('click', function (e) {
        const b = e.target.closest('.pu-copy');
        if (!b) return;
        navigator.clipboard.writeText(b.dataset.copy).then(() => { b.classList.add('is-done'); setTimeout(() => b.classList.remove('is-done'), 900); });
    });

    function step(name) {
        ['puStepSearch', 'puResults'].forEach(id => $(id).classList.toggle('is-hidden', id !== name));
    }

    function scheduleSearch() {
        clearTimeout(searchTimer);
        const q = $('puSearch').value.trim();
        if (q.length < 2) {
            $('puSearchResults').innerHTML = q.length ? '<div class="pu-loading">Type at least 2 characters.</div>' : '';
            return;
        }
        searchTimer = setTimeout(() => runSearch(q), 220);
    }

    async function runSearch(q) {
        const seq = ++searchSeq;
        const box = $('puSearchResults');
        box.innerHTML = '<div class="pu-loading"><div class="spinner-border spinner-border-sm"></div> Searching premium, paid content, orders and accounts...</div>';
        try {
            const res = await fetch(`/api/purchases/search-all?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            if (seq !== searchSeq) return;
            if (!res.ok) throw new Error(data.error || 'Search failed.');
            renderSearch(data, q);
        } catch (err) {
            if (seq !== searchSeq) return;
            box.innerHTML = `<div class="alert alert-danger mb-0">${esc(err.message || 'Search failed.')}</div>`;
        }
    }

    function renderSearch(rows, q) {
        const box = $('puSearchResults');
        if (!rows.length) {
            box.innerHTML = `<div class="pu-loading">Nothing matches <strong>${esc(q)}</strong> in premium, paid content, orders or accounts.
                <br><small>Have a Razorpay ID the database does not know? Use <b>Find by Payment ID</b> to check it at the gateway.</small></div>`;
            return;
        }
        let html = `<div class="pu-buyers__title">${rows.length} match(es)${rows.length >= 30 ? ' - showing the latest 30, keep typing to narrow' : ''}</div><div class="pu-buyers__grid">`;
        rows.forEach(r => {
            const chips = [];
            if (r.premium) chips.push(`<span class="pu-chip pu-chip--premium"><i class="fas fa-crown"></i> ${r.premium} premium</span>`);
            if (r.paid_items) chips.push(`<span class="pu-chip pu-chip--paid"><i class="fas fa-bag-shopping"></i> ${r.paid_items} paid item(s)</span>`);
            if (r.pending) chips.push(`<span class="pu-chip pu-chip--pending"><i class="fas fa-hourglass-half"></i> ${r.pending} unconfirmed</span>`);
            if (r.enrollments) chips.push(`<span class="pu-chip">${r.enrollments} enrollment fee(s)</span>`);
            if (!chips.length) chips.push(`<span class="pu-chip">${r.registered ? 'registered, nothing bought yet' : '-'}</span>`);
            html += `<button type="button" class="pu-buyer" data-email="${esc(r.email)}">
                        <strong>${esc(r.username || r.email)}</strong>
                        <span>${esc(r.email)}${r.phone ? ' · ' + esc(r.phone) : ''}</span>
                        <em>${chips.join(' ')}</em>
                        <small>${money(r.total_paid)} paid · last: ${esc(r.last_activity || '-')} · matched on ${esc((r.hit || []).join(', ') || 'account')}</small>
                     </button>`;
        });
        box.innerHTML = html + '</div>';
        box.querySelectorAll('.pu-buyer').forEach(el => el.addEventListener('click', () => openCustomer(el.dataset.email)));
    }

    async function openCustomer(email) {
        currentEmail = email;
        liveMap = {};
        log('open ' + email);
        try {
            const res = await fetch(`/api/purchases/customer-detail?email=${encodeURIComponent(email)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Lookup failed.');
            lastData = data;
            renderCustomer(data);
            loadLive(data);
        } catch (err) {
            say($('puMessage'), err.message || 'Could not load this customer.');
        }
    }

    function liveKeys(data) {
        const payments = new Set(), orders = new Set();
        data.purchases.forEach(p => { if (/^pay_/i.test(p.payment_id || '')) payments.add(p.payment_id); });
        data.subscriptions.forEach(s => {
            if (/^pay_/i.test(s.razorpay_payment_id || '')) payments.add(s.razorpay_payment_id);
            else if (/^order_/i.test(s.razorpay_order_id || '')) orders.add(s.razorpay_order_id);
        });
        data.orders.forEach(o => { if (/^order_/i.test(o.razorpay_order_id || '')) orders.add(o.razorpay_order_id); });
        data.enrollment_payments.forEach(e => { const pid = e.razorpay_payment_id || e.payment_id; if (/^pay_/i.test(pid || '')) payments.add(pid); });
        return { payments: [...payments], orders: [...orders] };
    }

    async function loadLive(data) {
        const keys = liveKeys(data);
        if (!keys.payments.length && !keys.orders.length) return;
        try {
            const res = await fetch(`/api/purchases/live?payments=${encodeURIComponent(keys.payments.join(','))}&orders=${encodeURIComponent(keys.orders.join(','))}`);
            const d = await res.json();
            if (!d.live) { say($('puMessage'), d.reason || 'Razorpay is not configured.'); liveMap = {}; }
            else liveMap = d.results || {};
        } catch (err) {
            liveMap = {};
        }
        if (lastData === data) renderCustomer(data);
    }

    function keyFor(row) {
        if (/^pay_/i.test(row.razorpay_payment_id || '')) return row.razorpay_payment_id;
        if (/^pay_/i.test(row.payment_id || '')) return row.payment_id;
        if (/^order_/i.test(row.razorpay_order_id || '')) return row.razorpay_order_id;
        return '';
    }

    function purchaseRow(p) {
        const key = keyFor(p);
        return `<tr>
            <td class="pu-nowrap">${esc(p.payment_date || '-')}</td>
            <td><strong>${esc(p.title)}</strong>${p.subtitle ? '<br><small class="text-muted">' + esc(p.subtitle) + '</small>' : ''}</td>
            <td><span class="pu-course-tag">${esc(p.course_code)}</span>${p.section ? '<br><small class="text-muted">' + esc(p.section) + '</small>' : ''}</td>
            <td class="pu-nowrap"><code>${esc(p.payment_id)}</code> ${copyBtn(p.payment_id)}</td>
            <td class="pu-nowrap">${Number(p.discount_percent) > 0
                ? `<span class="pu-old">${money(p.original_price)}</span> ${money(p.final_price)}<br><small class="text-success">${Number(p.discount_percent)}% off</small>`
                : money(p.final_price)}</td>
            <td>${gatewayCell(key)}</td>
            <td>${accessChip(p.access)}</td>
            <td>${verdictCell(key, p.access, 'paid')} ${liveBtn(key)}</td>
        </tr>`;
    }

    function subscriptionRow(s) {
        const key = keyFor(s);
        const period = s.starts_at ? `${esc(s.starts_at)} → ${esc(s.expires_at || '-')}` : 'not started';
        return `<tr class="${s.is_live ? 'pu-row--live' : ''}">
            <td class="pu-nowrap">${esc(s.created_at || '-')}</td>
            <td><strong><i class="fas fa-crown pu-crown"></i> ${esc(s.plan_label || s.plan)}</strong>${s.is_live ? ' <span class="badge bg-success">live now</span>' : ''}<br><small class="text-muted">${period}</small></td>
            <td><span class="pu-course-tag">${esc(s.course_code || 'all courses')}</span></td>
            <td class="pu-nowrap"><code>${esc(s.razorpay_payment_id || s.razorpay_order_id || '-')}</code> ${copyBtn(s.razorpay_payment_id || s.razorpay_order_id)}</td>
            <td class="pu-nowrap">${money(s.amount)}</td>
            <td>${gatewayCell(key)}</td>
            <td>${accessChip(s.access)}</td>
            <td>${verdictCell(key, s.access, 'premium')} ${liveBtn(key)}</td>
        </tr>`;
    }

    function orderRow(o) {
        const key = keyFor(o);
        return `<tr>
            <td class="pu-nowrap">${esc(o.created_at || '-')}</td>
            <td><strong>${esc(o.items || 'Course content')}</strong><br><small class="text-muted">stored: ${esc(o.status)}${o.gateway_status ? ' · gateway said ' + esc(o.gateway_status) : ''}</small></td>
            <td><span class="pu-course-tag">${esc(o.course_code)}</span></td>
            <td class="pu-nowrap"><code>${esc(o.razorpay_order_id)}</code> ${copyBtn(o.razorpay_order_id)}</td>
            <td class="pu-nowrap">${money(o.amount)}</td>
            <td>${gatewayCell(key)}</td>
            <td>${accessChip('not_granted')}</td>
            <td>${verdictCell(key, 'not_granted', 'order')}</td>
        </tr>`;
    }

    function enrollmentRow(e) {
        const pid = e.razorpay_payment_id || e.payment_id;
        const key = /^pay_/i.test(pid || '') ? pid : '';
        return `<tr>
            <td class="pu-nowrap">${esc(e.completion_date || '-')}</td>
            <td><strong>Platform enrollment fee</strong></td>
            <td><span class="pu-course-tag">${esc(e.course_code)}</span></td>
            <td class="pu-nowrap"><code>${esc(pid)}</code> ${copyBtn(pid)}</td>
            <td class="pu-nowrap">${money(e.amount_paid)}</td>
            <td>${gatewayCell(key)}</td>
            <td>${statusChip(e.payment_status)}</td>
            <td>${key ? liveBtn(key) : '<small class="text-muted">free enrolment</small>'}</td>
        </tr>`;
    }

    function liveBtn(key) {
        if (!key || !/^pay_/i.test(key)) return '';
        return `<button type="button" class="btn btn-outline-primary btn-sm pu-verify" data-pid="${esc(key)}" title="Full gateway record"><i class="fas fa-tower-broadcast"></i></button>`;
    }

    function tableWrap(title, rowsHtml, cls) {
        return `<div class="pu-section pu-section--${cls}">
            <h5 class="pu-table-title">${title}</h5>
            <div class="table-responsive pu-table-box">
            <table class="table table-sm table-hover pu-table">
            <thead><tr><th>Date &amp; Time</th><th>Item</th><th>Course</th><th>Transaction</th><th>Amount</th><th>Gateway (live)</th><th>Access</th><th>Verdict</th></tr></thead>
            <tbody>${rowsHtml}</tbody></table></div></div>`;
    }

    function renderCustomer(data) {
        const s = data.summary;
        const a = data.account || {};
        step('puResults');
        $('puCustomerLabel').textContent = `${s.username || currentEmail}`;
        $('puSummary').innerHTML = `
            <div class="pu-sum"><small>Customer</small><strong>${esc(s.username || '-')}</strong><span>${esc(currentEmail)} ${copyBtn(currentEmail)}</span></div>
            <div class="pu-sum"><small>Account</small><strong>${a.email ? esc(a.auth_type || 'manual') : 'no account'}</strong><span>${a.created_at ? 'since ' + esc(a.created_at) : '-'}${a.last_active ? '<br>last active ' + esc(a.last_active) : ''}</span></div>
            <div class="pu-sum pu-sum--premium"><small><i class="fas fa-crown"></i> Premium</small><strong>${s.premium_active ? '<span class="text-success">Active</span>' : 'None'}</strong><span>${s.premium_active ? 'in ' + esc(s.premium_courses.join(', ')) : s.subscriptions ? s.subscriptions + ' past / unconfirmed' : 'no subscription'}</span></div>
            <div class="pu-sum pu-sum--paid"><small><i class="fas fa-bag-shopping"></i> Paid content</small><strong>${s.items} item(s)</strong><span>${s.pending ? '<span class="text-warning">' + s.pending + ' unconfirmed order(s)</span>' : 'no unconfirmed orders'}</span></div>
            <div class="pu-sum"><small>Total paid</small><strong>${money(s.total_paid)}</strong><span>${s.enrollment_payments} enrollment fee(s)</span></div>`;
        $('puExportBtn').href = `/api/purchases/export-customer?email=${encodeURIComponent(currentEmail)}&course_code=`;

        let html = '';
        if (data.orders.length) html += tableWrap('<i class="fas fa-hourglass-half"></i> Unconfirmed orders - started but never recorded as paid', data.orders.map(orderRow).join(''), 'pending');
        html += data.subscriptions.length
            ? tableWrap('<i class="fas fa-crown"></i> Premium subscriptions', data.subscriptions.map(subscriptionRow).join(''), 'premium')
            : '<div class="pu-loading pu-section pu-section--premium"><i class="fas fa-crown"></i> No premium subscription.</div>';
        html += data.purchases.length
            ? tableWrap('<i class="fas fa-bag-shopping"></i> Paid content purchases', data.purchases.map(purchaseRow).join(''), 'paid')
            : '<div class="pu-loading pu-section pu-section--paid"><i class="fas fa-bag-shopping"></i> No paid content bought.</div>';
        if (data.enrollment_payments.length) html += tableWrap('Enrollment / platform fees', data.enrollment_payments.map(enrollmentRow).join(''), 'fees');
        $('puTables').innerHTML = html;
    }

    document.addEventListener('click', async function (e) {
        const g = e.target.closest('.pu-grant');
        const r = e.target.closest('.pu-revoke');
        if (!g && !r) return;
        const btn = g || r;
        const url = g ? '/api/purchases/grant' : '/api/purchases/revoke';
        const body = g ? { order_id: g.dataset.order } : { payment_id: r.dataset.pid };
        const question = g ? 'Razorpay will be asked again; if the payment is captured, access opens now. Continue?'
                           : 'Revoke this student\'s access for this payment?';
        if (!confirm(question)) return;
        btn.disabled = true;
        try {
            const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(body) });
            const d = await res.json();
            say($('puMessage'), d.message || (d.success ? 'Done.' : 'Refused.'), d.success ? 'success' : 'danger');
            if (d.success) {
                if (currentEmail && views.lookup.classList.contains('is-active')) openCustomer(currentEmail);
                if (views.attention.classList.contains('is-active')) scanAttention();
            }
        } catch (err) {
            say($('puMessage'), 'Could not reach the server.');
        } finally {
            btn.disabled = false;
        }
    });

    async function scanAttention() {
        const box = $('puAttentionList');
        box.innerHTML = '<div class="pu-loading"><div class="spinner-border spinner-border-sm"></div> Comparing the last 30 days with Razorpay...</div>';
        $('puAttentionMeta').textContent = '';
        try {
            const res = await fetch('/api/purchases/attention');
            const d = await res.json();
            if (!d.live) { box.innerHTML = `<div class="alert alert-secondary mb-0">${esc(d.reason || 'Razorpay is not configured.')}</div>`; return; }
            $('puAttentionMeta').textContent = `${d.scanned} record(s) compared · ${d.items.length} need attention · ${new Date().toLocaleTimeString()}`;
            if (!d.items.length) { box.innerHTML = '<div class="pu-loading pu-ok"><i class="fas fa-circle-check"></i> Everything matches Razorpay. Nothing to fix.</div>'; return; }
            let html = '<div class="table-responsive pu-table-box"><table class="table table-sm table-hover pu-table"><thead><tr><th>When</th><th>Student</th><th>What</th><th>Course</th><th>Amount</th><th>Gateway (live)</th><th>Access</th><th>Verdict</th></tr></thead><tbody>';
            d.items.forEach(it => {
                const gw = it.gateway || {}; const v = it.verdict || {};
                const action = v.action === 'grant'
                    ? `<button type="button" class="btn btn-warning btn-sm pu-grant" data-order="${esc(it.razorpay_order_id)}"><i class="fas fa-unlock"></i> Grant access</button>`
                    : v.action === 'revoke' ? `<button type="button" class="btn btn-danger btn-sm pu-revoke" data-pid="${esc(gw.payment_id || it.razorpay_payment_id)}"><i class="fas fa-ban"></i> Revoke</button>` : '';
                html += `<tr>
                    <td class="pu-nowrap">${esc(it.created_at)}</td>
                    <td><button type="button" class="btn btn-link btn-sm p-0 pu-open" data-email="${esc(it.email)}">${esc(it.username || it.email)}</button><br><small class="text-muted">${esc(it.email)}</small></td>
                    <td>${it.kind === 'premium' ? '<i class="fas fa-crown pu-crown"></i> Premium' : '<i class="fas fa-bag-shopping"></i> Paid content'}<br><code>${esc(it.razorpay_payment_id || it.razorpay_order_id)}</code></td>
                    <td><span class="pu-course-tag">${esc(it.course_code || '-')}</span></td>
                    <td class="pu-nowrap">${money((it.amount_paise || 0) / 100)}</td>
                    <td>${statusChip(gw.refund_status === 'full' ? 'refunded' : gw.status)}</td>
                    <td>${accessChip(it.status === 'paid' || it.status === 'active' ? 'granted' : 'not_granted')}</td>
                    <td><span class="pu-verdict pu-verdict--${esc(v.kind)}">${esc(v.text)}</span> ${action}</td>
                </tr>`;
            });
            box.innerHTML = html + '</tbody></table></div>';
            box.querySelectorAll('.pu-open').forEach(b => b.addEventListener('click', () => { showView('lookup'); openCustomer(b.dataset.email); }));
        } catch (err) {
            box.innerHTML = '<div class="alert alert-danger mb-0">Could not reach the server.</div>';
        }
    }
    $('puAttentionScanBtn').addEventListener('click', scanAttention);

    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('.pu-verify');
        if (!btn) return;
        const pid = btn.dataset.pid;
        const body = $('puVerifyBody');
        body.innerHTML = '<div class="text-center p-3"><div class="spinner-border text-primary"></div><p class="mt-2 mb-0">Asking Razorpay...</p></div>';
        const modal = new bootstrap.Modal($('puVerifyModal'));
        modal.show();
        try {
            const res = await fetch('/api/purchases/verify/' + encodeURIComponent(pid));
            const d = await res.json();
            if (!d.live) { body.innerHTML = `<div class="alert alert-secondary mb-0"><i class="fas fa-circle-info me-1"></i> ${esc(d.reason)}</div>`; return; }
            let rows = `
                <div class="alert alert-${d.verdict_kind} pu-verdict"><i class="fas fa-circle-check me-1"></i> ${esc(d.verdict)}</div>
                <table class="table table-sm pu-verify-table"><tbody>
                <tr><th>Payment ID</th><td><code>${esc(d.payment_id)}</code></td></tr>
                <tr><th>Gateway status</th><td>${statusChip(d.status)} ${d.captured ? '<span class="badge bg-success">captured</span>' : ''}</td></tr>
                <tr><th>Amount</th><td>${money(d.amount)} ${d.currency ? esc(d.currency) : ''}</td></tr>
                ${d.amount_refunded > 0 ? `<tr><th>Refunded</th><td class="text-danger">${money(d.amount_refunded)}</td></tr>` : ''}
                <tr><th>Method</th><td>${esc(d.method || '-')}</td></tr>
                <tr><th>Paid at</th><td>${esc(d.created_at || '-')}</td></tr>
                <tr><th>Payer email</th><td>${esc(d.email || '-')}</td></tr>
                <tr><th>Payer contact</th><td>${esc(d.contact || '-')}</td></tr>
                <tr><th>Order ID</th><td><code>${esc(d.order_id || '-')}</code></td></tr>`;
            if (d.error_description) rows += `<tr><th>Failure reason</th><td class="text-danger">${esc(d.error_description)} <small>(${esc(d.error_code || '')} ${esc(d.error_reason || '')})</small></td></tr>`;
            body.innerHTML = rows + '</tbody></table>';
        } catch (err) {
            body.innerHTML = '<div class="alert alert-danger mb-0">Could not reach the server. Try again.</div>';
        }
    });

    async function findByPayment() {
        const pid = $('puPaymentId').value.trim();
        if (!pid) { say($('puPaymentMessage'), 'Enter a payment ID first.'); return; }
        const box = $('puPaymentResults');
        box.innerHTML = '<div class="pu-loading"><div class="spinner-border spinner-border-sm"></div> Searching...</div>';
        try {
            const res = await fetch('/api/purchases/find?payment_id=' + encodeURIComponent(pid));
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Search failed.');
            if (!data.found) {
                box.innerHTML = `<div class="alert alert-warning mb-0"><i class="fas fa-triangle-exclamation me-1"></i>
                    No record of <code>${esc(pid)}</code> in the database.
                    <button type="button" class="btn btn-primary btn-sm ms-2 pu-verify" data-pid="${esc(pid)}"><i class="fas fa-tower-broadcast"></i> Check at Razorpay anyway</button></div>`;
                return;
            }
            const who = (data.purchases[0] || data.enrollment_payments[0] || {}).email;
            box.innerHTML = `<div class="alert alert-success mb-2"><i class="fas fa-circle-check me-1"></i> Found for <strong>${esc(who)}</strong> - opening the customer with live gateway status.</div>`;
            if (who) { showView('lookup'); openCustomer(who); }
        } catch (err) {
            box.innerHTML = '';
            say($('puPaymentMessage'), err.message || 'Search failed.');
        }
    }
    $('puFindPaymentBtn').addEventListener('click', findByPayment);
    $('puPaymentId').addEventListener('keydown', e => { if (e.key === 'Enter') findByPayment(); });

    $('puSearch').addEventListener('input', scheduleSearch);
    $('puSearch').addEventListener('keydown', e => {
        if (e.key === 'Enter') { clearTimeout(searchTimer); const q = $('puSearch').value.trim(); if (q.length >= 2) runSearch(q); }
    });
    $('puBackToSearchBtn').addEventListener('click', () => { step('puStepSearch'); $('puSearch').focus(); });
    $('puRefreshLiveBtn').addEventListener('click', () => { if (currentEmail) openCustomer(currentEmail); });

    $('puCopySummaryBtn').addEventListener('click', () => {
        if (!lastData) return;
        const s = lastData.summary;
        let text = `Customer summary for ${currentEmail}\n`;
        text += `Name: ${s.username || '-'} | Paid items: ${s.items} | Premium: ${s.premium_active ? 'active in ' + s.premium_courses.join(', ') : 'none'} | Total paid: Rs.${Number(s.total_paid).toFixed(2)}\n\n`;
        lastData.subscriptions.forEach(x => {
            const gw = liveMap[keyFor(x)] || {};
            text += `- ${x.created_at} | Premium ${x.plan_label || x.plan} (${x.course_code || 'all'}) ${x.starts_at || '-'} to ${x.expires_at || '-'} | Rs.${Number(x.amount).toFixed(2)} | ${x.razorpay_payment_id || x.razorpay_order_id || '-'} | stored: ${x.status} | gateway: ${gw.status || '?'}\n`;
        });
        lastData.purchases.forEach(p => {
            const gw = liveMap[keyFor(p)] || {};
            text += `- ${p.payment_date} | ${p.title} | ${p.course_code} | Rs.${Number(p.final_price).toFixed(2)} | ${p.payment_id} | stored: ${p.status} | gateway: ${gw.status || '?'}\n`;
        });
        lastData.orders.forEach(o => {
            const gw = liveMap[keyFor(o)] || {};
            text += `- ${o.created_at} | UNCONFIRMED ${o.items} | ${o.course_code} | Rs.${Number(o.amount).toFixed(2)} | ${o.razorpay_order_id} | gateway: ${gw.status || '?'}\n`;
        });
        navigator.clipboard.writeText(text).then(() => say($('puMessage'), 'Support summary copied to clipboard.', 'success'));
    });

    $('puSearch').focus();
});
