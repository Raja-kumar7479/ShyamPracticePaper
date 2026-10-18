(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const CAN_MANAGE = document.body.dataset.canManage === 'true';
    const log = (...a) => console.log('[PREMIUM]', ...a);

    let courses = {};
    let plansByCode = {};
    let active = null;
    let quill = null;
    let messageTimer = null;
    let today = null;
    let todayLabel = '';

    const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

    function hideMessage() {
        const m = $('pcMessage');
        m.classList.add('is-hidden'); m.innerHTML = '';
        if (messageTimer) { clearTimeout(messageTimer); messageTimer = null; }
    }

    function message(kind, text) {
        if (typeof window.adminToast === 'function') {
            window.adminToast(text, kind === 'ok' ? 'success' : 'danger');
            return;
        }
        const m = $('pcMessage');
        if (messageTimer) { clearTimeout(messageTimer); messageTimer = null; }
        m.className = 'pc-message is-' + kind;
        m.innerHTML = '<span class="pc-message__text"></span>';
        m.querySelector('.pc-message__text').textContent = text;
        if (kind === 'ok') messageTimer = setTimeout(hideMessage, 6000);
    }

    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const baseDay = () => today || midnight(new Date());
    const plural = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');

    function showDate(value) {
        if (!value) return '(none)';
        const d = value instanceof Date ? value : new Date(value);
        if (isNaN(d)) return String(value);
        const two = (n) => String(n).padStart(2, '0');
        let text = two(d.getDate()) + ' ' + MONTHS[d.getMonth()] + ' ' + d.getFullYear();
        if (!(value instanceof Date)) {
            const h = d.getHours() % 12 || 12;
            text += ', ' + two(h) + ':' + two(d.getMinutes()) + (d.getHours() < 12 ? ' AM' : ' PM');
        }
        return text;
    }

    function addMonths(day, n) {
        const first = new Date(day.getFullYear(), day.getMonth() + n, 1);
        const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
        return new Date(first.getFullYear(), first.getMonth(), Math.min(day.getDate(), last));
    }

    function span(end) {
        const base = baseDay();
        const last = midnight(end);
        const days = Math.round((last - base) / 86400000);
        if (days <= 0) return { days: days, text: '' };
        let months = (last.getFullYear() - base.getFullYear()) * 12 + (last.getMonth() - base.getMonth());
        if (addMonths(base, months) > last) months -= 1;
        const rest = Math.round((last - addMonths(base, months)) / 86400000);
        const bits = [];
        if (Math.floor(months / 12)) bits.push(plural(Math.floor(months / 12), 'year'));
        if (months % 12) bits.push(plural(months % 12, 'month'));
        if (rest || !bits.length) bits.push(plural(rest, 'day'));
        return { days: days, text: bits.join(' ') };
    }

    function planEnd(validUntil, extra) {
        if (!validUntil) return null;
        const end = new Date(validUntil);
        if (isNaN(end)) return null;
        end.setDate(end.getDate() + (parseInt(extra, 10) || 0));
        return end;
    }

    function planSummary(p) {
        const bits = [money(p.payable)];
        if (p.discount > 0) bits.push(p.discount + '% off');
        if (p.ends_at) bits.push('access until ' + p.ends_at);
        bits.push(p.days + ' days' + (p.span ? ' (' + p.span + ')' : '') + ' from today');
        if (p.expired) bits.push('date passed');
        return bits.join(' · ');
    }

    function paintStates() {
        Object.keys(courses).forEach(code => {
            const el = document.querySelector(`[data-state-for="${code}"]`);
            if (!el) return;
            const list = (plansByCode[code] || []).filter(p => !p.expired);
            el.className = 'pc-course__state';
            if (!list.length) { el.textContent = 'No plan set - students see "coming soon"'; el.classList.add('is-off'); return; }
            el.textContent = list.length + ' plan' + (list.length === 1 ? '' : 's') + ' · from '
                + money(Math.min.apply(null, list.map(p => p.payable)));
            el.classList.add('is-set');
        });
    }

    function rowValues(row) {
        const v = {};
        row.querySelectorAll('[data-f]').forEach(el => { v[el.dataset.f] = el.value; });
        return v;
    }

    function refreshDays(row) {
        const v = rowValues(row);
        const out = row.querySelector('[data-days]');
        const note = row.querySelector('[data-span]');
        const end = planEnd(v.valid_until, v.extra_days);
        const s = end ? span(end) : null;
        if (out) out.value = !s ? '-' : (s.days <= 0 ? '0 (date passed)' : String(s.days));
        if (note) note.textContent = s && s.days > 0 ? '= ' + s.text + ' · ends ' + showDate(midnight(end)) : '';
    }

    function setMinimumDates(row) {
        const d = baseDay();
        const floor = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') + 'T00:00';
        row.querySelectorAll('[data-f="valid_until"], [data-f="discount_ends_at"]').forEach(el => { el.min = floor; });
    }

    function fillRow(row, plan) {
        row.dataset.planId = plan && plan.id ? plan.id : '';
        row.querySelectorAll('[data-f]').forEach(el => {
            let value = plan ? plan[el.dataset.f] : '';
            if (value === null || value === undefined) value = '';
            el.value = value;
        });
        const note = row.querySelector('[data-note]');
        if (note) note.textContent = plan ? planSummary(plan) : 'New plan - not saved yet';
        setMinimumDates(row);
        refreshDays(row);
    }

    function bindRow(row) {
        row.querySelector('[data-act="save"]').addEventListener('click', () => savePlan(row));
        row.querySelector('[data-act="delete"]').addEventListener('click', () => deletePlan(row));
        row.querySelectorAll('[data-f="valid_until"], [data-f="extra_days"]').forEach(el => {
            el.addEventListener('input', () => refreshDays(row));
        });
    }

    function addRow(plan) {
        const tpl = $('pcPlanTemplate');
        const row = tpl.content.firstElementChild.cloneNode(true);
        fillRow(row, plan);
        bindRow(row);
        $('pcPlanList').appendChild(row);
        return row;
    }

    function renderPlans(code) {
        $('pcPlanList').innerHTML = '';
        (plansByCode[code] || []).forEach(addRow);
        if (!(plansByCode[code] || []).length) addRow(null);
        lockCopy(code);
    }

    function lockCopy(code) {
        const locked = !(plansByCode[code] || []).some(p => p.id);
        $('pcCopy').disabled = locked;
        $('pcCopy').classList.toggle('is-locked', locked);
        $('pcCopyLocked').classList.toggle('is-hidden', !locked);
        if (quill) quill.enable(!locked);
    }

    const confirmAction = (opts) => (window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title)));

    function planChanges(saved, payload) {
        const same = (a, b) => String(a == null ? '' : a).trim() === String(b == null ? '' : b).trim();
        const num = (a) => Number(a || 0);
        const out = [];
        if (!same(saved.label, payload.label)) out.push({ label: 'Plan name', from: saved.label, to: payload.label });
        if (num(saved.price) !== num(payload.price)) out.push({ label: 'Amount', from: money(saved.price), to: money(payload.price) });
        if (num(saved.discount) !== num(payload.discount)) out.push({ label: 'Discount', from: num(saved.discount) + '%', to: num(payload.discount) + '%' });
        if (num(payload.discount) > 0 && !same(saved.discount_ends_at, payload.discount_ends_at)) {
            out.push({ label: 'Discount ends', from: showDate(saved.discount_ends_at), to: showDate(payload.discount_ends_at) });
        }
        if (!same(saved.valid_until, payload.valid_until)) out.push({ label: 'Valid until', from: showDate(saved.valid_until), to: showDate(payload.valid_until) });
        if (num(saved.extra_days) !== num(payload.extra_days)) out.push({ label: 'Extra days', from: String(num(saved.extra_days)), to: String(num(payload.extra_days)) });
        return out;
    }

    function holderText(h) {
        const total = h.active + h.pending;
        if (!total) return 'No student has bought this plan yet, so the new terms apply to everyone who buys from now on.';
        const parts = [];
        if (h.active) parts.push(plural(h.active, 'student') + ' already ' + (h.active === 1 ? 'has' : 'have') + ' this plan');
        if (h.pending) parts.push(plural(h.pending, 'student') + ' ' + (h.pending === 1 ? 'is' : 'are') + ' paying for it right now');
        return parts.join(' and ') + '. They keep the amount they paid and their own end date - nothing changes for them. '
            + 'The new terms apply only to students who buy from now on.';
    }

    async function fetchHolders(id) {
        const r = await fetch('/api/premium-catalog/' + encodeURIComponent(active) + '/plans/' + id + '/holders',
                              { headers: { 'Accept': 'application/json' } });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.success) throw new Error(data.message || 'Could not check who bought this plan.');
        return data.holders;
    }

    async function savePlan(row) {
        if (!CAN_MANAGE) { message('bad', 'Your role cannot change premium settings.'); return; }
        const v = rowValues(row);
        const payload = {
            id: row.dataset.planId || null,
            label: (v.label || '').trim(), price: v.price, discount: v.discount || '0',
            discount_ends_at: v.discount_ends_at || '', valid_until: v.valid_until || '',
            extra_days: v.extra_days || '0'
        };
        const missing = [];
        if (!payload.label) missing.push('Plan name');
        if (!parseFloat(payload.price)) missing.push('Amount');
        if (!payload.valid_until) missing.push('Valid until');
        if (parseFloat(payload.discount) > 0 && !payload.discount_ends_at) missing.push('Discount valid until');
        if (missing.length) { message('bad', 'Required: ' + missing.join(', ') + '.'); return; }

        const end = planEnd(payload.valid_until, payload.extra_days);
        const s = span(end);
        const lengthText = s.days > 0 ? s.days + ' days (' + s.text + '), until ' + showDate(midnight(end)) : 'the date has already passed';
        const saved = payload.id ? (plansByCode[active] || []).find(p => String(p.id) === String(payload.id)) : null;
        let holders = { active: 0, pending: 0 };
        let opts;
        if (saved) {
            const changes = planChanges(saved, payload);
            if (!changes.length) { message('ok', 'No changes to save for "' + saved.label + '".'); return; }
            try { holders = await fetchHolders(payload.id); } catch (err) { message('bad', err.message); return; }
            opts = {
                tone: 'primary',
                title: 'Save changes to the plan "' + saved.label + '"?',
                message: holderText(holders),
                itemsTitle: 'What changes for new buyers',
                items: changes.concat([{ label: 'New buyers get', value: lengthText }]),
                note: 'Today is ' + (todayLabel || showDate(baseDay())) + '. Days are counted from today.',
                confirmText: 'Save for new buyers'
            };
        } else {
            opts = {
                tone: 'primary',
                icon: 'fa-plus',
                title: 'Put the plan "' + payload.label + '" on sale?',
                items: [
                    { label: 'Amount', value: money(payload.price) + (parseFloat(payload.discount) > 0 ? ' - ' + parseFloat(payload.discount) + '% off until ' + showDate(payload.discount_ends_at) : '') },
                    { label: 'Access', value: lengthText }
                ],
                note: 'Today is ' + (todayLabel || showDate(baseDay())) + '. Days are counted from today.',
                confirmText: 'Save plan'
            };
        }
        if (!(await confirmAction(opts))) return;

        for (let attempt = 0; attempt < 2; attempt++) {
            payload.approved_holders = holders.active + holders.pending;
            let r, data;
            try {
                r = await fetch('/api/premium-catalog/' + encodeURIComponent(active) + '/plans', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify(payload)
                });
                data = await r.json().catch(() => ({}));
            } catch (err) {
                message('bad', 'Network error - the plan was not saved.');
                return;
            }
            if (r.status === 409 && data.needs_approval && attempt === 0) {
                holders = data.holders;
                opts.message = 'The number of buyers changed while you were deciding. ' + holderText(holders);
                if (!(await confirmAction(opts))) return;
                continue;
            }
            if (!r.ok || !data.success) { message('bad', data.message || 'Could not save the plan.'); return; }
            plansByCode[active] = data.plans;
            renderPlans(active); paintStates();
            message('ok', data.message);
            log('plan saved', active, payload.label);
            return;
        }
    }

    async function deletePlan(row) {
        if (!CAN_MANAGE) { message('bad', 'Your role cannot change premium settings.'); return; }
        const id = row.dataset.planId;
        if (!id) { row.remove(); return; }
        const saved = (plansByCode[active] || []).find(p => String(p.id) === String(id));
        let holders;
        try { holders = await fetchHolders(id); } catch (err) { message('bad', err.message); return; }
        const total = holders.active + holders.pending;
        const approved = await confirmAction({
            tone: 'danger',
            title: 'Stop selling the plan "' + (saved ? saved.label : 'this plan') + '"?',
            message: total
                ? plural(total, 'student') + ' who bought it or are paying for it keep their access until their own end date. New students will no longer see it.'
                : 'No student has bought it. New students will no longer see it.',
            note: 'This cannot be undone.',
            confirmText: 'Remove plan'
        });
        if (!approved) return;
        try {
            const r = await fetch('/api/premium-catalog/' + encodeURIComponent(active) + '/plans/' + id, {
                method: 'DELETE', headers: { 'X-CSRFToken': csrf() }
            });
            const data = await r.json();
            if (!r.ok || !data.success) { message('bad', data.message || 'Could not delete the plan.'); return; }
            plansByCode[active] = data.plans;
            renderPlans(active); paintStates();
            message('ok', data.message);
        } catch (err) {
            message('bad', 'Network error - the plan was not deleted.');
        }
    }

    function csrf() {
        return window.ADMIN_CSRF || (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    }

    function open(code) {
        active = code;
        document.querySelectorAll('.pc-course').forEach(b => b.classList.toggle('is-active', b.dataset.code === code));
        $('pcEmpty').classList.add('is-hidden');
        $('pcForm').classList.remove('is-hidden');
        $('pcTitle').textContent = (courses[code] && courses[code].name) || code;
        $('pcCode').textContent = code;
        $('pcSaveCode').textContent = code;
        const row = courses[code] && courses[code].row;
        $('pcHeadline').value = (row && row.headline) || '';
        if (!quill) {
            quill = new Quill('#pcDetails', { theme: 'snow', placeholder: 'What does a premium student get in this course?',
                                              modules: { toolbar: '#pcToolbar' } });
        }
        quill.root.innerHTML = (row && row.details) || '';
        $('pcSavedAt').textContent = row && row.updated_at ? 'Last saved ' + row.updated_at : 'Not saved yet';
        hideMessage();
        renderPlans(code);
        log('opened', code, (plansByCode[code] || []).length, 'plan(s)');
    }

    async function load() {
        const r = await fetch('/api/premium-catalog');
        const data = await r.json();
        courses = {}; plansByCode = {};
        if (data.today) {
            const parts = data.today.split('-').map(Number);
            today = new Date(parts[0], parts[1] - 1, parts[2]);
            todayLabel = data.today_label || '';
            if ($('pcTodayLabel') && todayLabel) $('pcTodayLabel').textContent = todayLabel;
        }
        (data.courses || []).forEach(c => { courses[c.code] = c; plansByCode[c.code] = c.plans || []; });
        paintStates();
        if (active) open(active);
        log('loaded', Object.keys(courses).length, 'course(s)');
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.pc-course').forEach(b => b.addEventListener('click', () => open(b.dataset.code)));
        $('pcAddPlan').addEventListener('click', () => addRow(null));
        $('pcForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            if (!CAN_MANAGE) { message('bad', 'Your role cannot change premium settings.'); return; }
            const headline = $('pcHeadline').value.trim();
            const details = quill && quill.getLength() > 1 ? quill.root.innerHTML : '';
            const missing = [];
            if (!headline) missing.push('Headline');
            if (!details) missing.push('What you get');
            if (missing.length) { message('bad', 'Required: ' + missing.join(', ') + '.'); return; }
            $('pcSave').disabled = true;
            try {
                const r = await fetch('/api/premium-catalog/' + encodeURIComponent(active) + '/copy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify({ headline: headline, details: details })
                });
                const data = await r.json();
                if (!r.ok || !data.success) { message('bad', data.message || 'Could not save.'); return; }
                courses[active].row = data.row;
                $('pcSavedAt').textContent = 'Last saved ' + (data.row.updated_at || 'just now');
                message('ok', data.message);
            } catch (err) {
                message('bad', 'Network error - nothing was saved.');
            } finally {
                $('pcSave').disabled = false;
            }
        });
        load();
    });
})();
