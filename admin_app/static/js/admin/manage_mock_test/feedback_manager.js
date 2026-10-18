document.addEventListener('DOMContentLoaded', function () {

    const $ = (id) => document.getElementById(id);
    const log = (m, x) => console.log('[FEEDBACK] ' + m, x === undefined ? '' : x);

    let courseCode = '', courseName = '', testKey = '', testTitle = '';
    let entries = [];
    let current = null;
    let quill = null;
    let logsLoaded = false;
    let logStudents = [];

    const fbViews = {
        feedback: $('fbView-feedback'),
        logs: $('fbView-logs')
    };
    document.querySelectorAll('.as-view[data-view]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const target = btn.dataset.view;
            if (!fbViews[target]) return;
            log('switching view -> ' + target);
            document.querySelectorAll('.as-view[data-view]').forEach(b => b.classList.toggle('is-active', b === btn));
            Object.keys(fbViews).forEach(k => fbViews[k].classList.toggle('is-active', k === target));
            if (window.matchMedia('(max-width: 991px)').matches && window.asClose) window.asClose();
            window.scrollTo({ top: 0, behavior: 'smooth' });
            if (target === 'logs' && !logsLoaded) loadLogCourses();
        });
    });

    function esc(v) {
        const d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }

    function say(el, text, kind) {
        el.className = 'alert mt-3 alert-' + (kind || 'danger');
        el.textContent = text;
        el.classList.remove('is-hidden');
        setTimeout(() => el.classList.add('is-hidden'), 6000);
    }

    function stars(rating) {
        if (rating == null) return '<span class="fb-norate">Not rated</span>';
        const full = Math.round(rating);
        let s = '';
        for (let i = 1; i <= 5; i++) {
            s += `<i class="fa${i <= full ? 's' : 'r'} fa-star"></i>`;
        }
        const kind = rating >= 4 ? 'good' : (rating <= 2 ? 'bad' : 'mid');
        return `<span class="fb-stars fb-stars--${kind}">${s} <b>${rating}</b>/5</span>`;
    }

    async function loadCourses() {
        try {
            const res = await fetch('/api/feedback/courses');
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            const grid = $('fbCourseGrid');
            grid.innerHTML = '';
            if (!data.length) {
                grid.innerHTML = '<div class="fb-loading">No feedback submitted yet.</div>';
                return;
            }
            data.forEach(c => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'fb-pick';
                b.innerHTML = `<span class="fb-pick__code">${esc(c.code)}</span>
                               <span class="fb-pick__name">${esc(c.name || c.code)}</span>
                               <span class="fb-pick__meta">${c.feedback_count} feedback</span>`;
                b.addEventListener('click', () => pickCourse(c.code, c.name || c.code));
                grid.appendChild(b);
            });
            log('courses loaded', data.length);
        } catch (e) {
            $('fbCourseGrid').innerHTML = '<div class="alert alert-danger mb-0">Could not load courses.</div>';
        }
    }

    let sectionId = '', contentTitle = '';

    async function pickCourse(code, name) {
        courseCode = code; courseName = name;
        sectionId = ''; contentTitle = '';
        log('course picked', code);
        $('fbStepCourse').classList.add('is-hidden');
        $('fbStepTest').classList.add('is-hidden');
        $('fbStepList').classList.add('is-hidden');
        $('fbStepContent').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Choose the course content';
        $('fbCourseLabel').textContent = `${code} - ${name}`;
        const grid = $('fbContentGrid');
        grid.innerHTML = '<div class="fb-loading"><div class="spinner-border spinner-border-sm"></div> Loading content...</div>';
        try {
            const res = await fetch('/api/feedback/contents?course_code=' + encodeURIComponent(code));
            const data = await res.json();
            grid.innerHTML = '';
            if (!data.length) {
                grid.innerHTML = '<div class="fb-loading">No feedback for this course yet.</div>';
                return;
            }
            data.forEach(c => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'fb-pick';
                const tag = c.label === 'Paid' ? ' · Paid' : ' · Free';
                b.innerHTML = `<span class="fb-pick__name">${esc(c.title || c.section_id)}</span>
                               <span class="fb-pick__sub">${esc(c.subtitle || '')}</span>
                               <span class="fb-pick__meta">${c.feedback_count} feedback${tag} · last ${esc(c.last_feedback || '-')}</span>`;
                b.addEventListener('click', () => pickContent(c.section_id, c.title || c.section_id));
                grid.appendChild(b);
            });
        } catch (e) {
            grid.innerHTML = '<div class="alert alert-danger mb-0">Could not load the course content.</div>';
        }
    }

    async function pickContent(id, title) {
        sectionId = id; contentTitle = title;
        log('content picked', id);
        $('fbStepContent').classList.add('is-hidden');
        $('fbStepList').classList.add('is-hidden');
        $('fbStepTest').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Choose a test';
        $('fbContentLabel').textContent = `${courseCode} · ${title}`;
        const grid = $('fbTestGrid');
        grid.innerHTML = '<div class="fb-loading"><div class="spinner-border spinner-border-sm"></div> Loading tests...</div>';
        try {
            const res = await fetch('/api/feedback/tests?course_code=' + encodeURIComponent(courseCode)
                                    + '&section_id=' + encodeURIComponent(id));
            const data = await res.json();
            grid.innerHTML = '';
            if (!data.length) {
                grid.innerHTML = '<div class="fb-loading">No feedback for this course yet.</div>';
                return;
            }
            data.forEach(t => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'fb-pick';
                b.innerHTML = `<span class="fb-pick__name">${esc(t.subject_title || 'Test ' + t.test_key)}</span>
                               <span class="fb-pick__sub">${esc(t.subject_subtitle || '')}</span>
                               <span class="fb-pick__meta">${t.feedback_count} feedback · last ${esc(t.last_feedback || '-')}</span>`;
                b.addEventListener('click', () => pickTest(t.test_key, t.subject_title || ('Test ' + t.test_key)));
                grid.appendChild(b);
            });
        } catch (e) {
            grid.innerHTML = '<div class="alert alert-danger mb-0">Could not load tests.</div>';
        }
    }

    async function pickTest(key, title) {
        testKey = key; testTitle = title;
        log('test picked', key);
        $('fbStepTest').classList.add('is-hidden');
        $('fbStepList').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Feedback';
        $('fbTestLabel').textContent = `${courseCode} · ${contentTitle} · ${title}`;
        await loadEntries();
    }

    async function loadEntries() {
        const list = $('fbList');
        list.innerHTML = '<div class="fb-loading"><div class="spinner-border spinner-border-sm"></div> Loading feedback...</div>';
        try {
            const res = await fetch('/api/feedback/entries?test_key=' + encodeURIComponent(testKey));
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            entries = data.feedbacks;
            const s = data.summary;
            $('fbSummary').innerHTML = `
                <div class="fb-sum"><small>Responses</small><strong>${s.count}</strong></div>
                <div class="fb-sum"><small>Average rating</small><strong>${s.average != null ? s.average + ' / 5' : '-'}</strong></div>
                <div class="fb-sum fb-sum--good"><small>Happy (4-5)</small><strong>${s.happy}</strong></div>
                <div class="fb-sum fb-sum--bad"><small>Unhappy (1-2)</small><strong>${s.unhappy}</strong></div>`;
            render();
        } catch (e) {
            list.innerHTML = '<div class="alert alert-danger mb-0">Could not load feedback.</div>';
        }
    }

    function render() {
        const filter = $('fbFilter').value;
        let rows = entries.slice();
        if (filter === 'happy') rows = rows.filter(r => r.rating != null && r.rating >= 4);
        else if (filter === 'unhappy') rows = rows.filter(r => r.rating != null && r.rating <= 2);
        else if (filter === 'suggestions') rows = rows.filter(r => (r.suggestions || '').trim());

        const list = $('fbList');
        if (!rows.length) {
            list.innerHTML = '<div class="fb-loading">No feedback matches this filter.</div>';
            return;
        }
        list.innerHTML = rows.map(r => `
            <div class="fb-item">
                <div class="fb-item__head">
                    <div class="fb-who">
                        <span class="fb-avatar">${esc((r.display_name || '?')[0].toUpperCase())}</span>
                        <div>
                            <strong>${esc(r.display_name)}</strong>
                            <span class="fb-email">${esc(r.email)}</span>
                        </div>
                    </div>
                    <div class="fb-rate">${stars(r.rating)}<small>${esc(r.submission_time || '')}</small></div>
                </div>
                <div class="fb-chips">
                    <span class="fb-chip"><b>Software:</b> ${esc(r.feedback_software || '-')}</span>
                    <span class="fb-chip"><b>Content:</b> ${esc(r.feedback_content || '-')}</span>
                    <span class="fb-chip"><b>Speed:</b> ${esc(r.feedback_speed || '-')}</span>
                </div>
                ${(r.suggestions || '').trim()
                    ? `<div class="fb-sugg"><i class="fas fa-quote-left"></i> ${esc(r.suggestions)}</div>` : ''}
                <div class="fb-actions">
                    <button type="button" class="btn btn-primary btn-sm fb-reply" data-id="${r.id}">
                        <i class="fas fa-paper-plane me-1"></i> Send Thank-You
                    </button>
                    <button type="button" class="btn btn-outline-danger btn-sm fb-del ms-auto" data-id="${r.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`).join('');
    }

    function initQuill() {
        if (quill || !window.Quill) return;
        quill = new Quill('#fbEditor', {
            theme: 'snow',
            modules: { toolbar: '#fbEditorToolbar' }
        });
    }

    function template(kind, r) {
        const name = r.display_name;
        const test = testTitle;
        const rating = r.rating != null ? r.rating : null;
        const common = `<p>Thank you for visiting <strong>ShyamPracticePaper</strong>. Please share it with your friends who are preparing too - it genuinely helps us grow.</p>
<p>Best wishes for your preparation,<br><strong>Team ShyamPracticePaper</strong></p>`;

        if (kind === 'praise') {
            return `<p>Hi ${esc(name)},</p>
<p>I saw your feedback on <strong>${esc(test)}</strong>${rating ? ` and the <strong>${rating}/5</strong> rating you gave` : ''} - thank you so much! Reviews like yours tell us the effort behind these tests is paying off.</p>
${common}`;
        }
        if (kind === 'apology') {
            return `<p>Hi ${esc(name)},</p>
<p>Thank you for taking the time to give feedback on <strong>${esc(test)}</strong>. I have read your points carefully and I am sorry the experience fell short.</p>
<p>Your comments are already with our content team and we are working on them for the next update. If you would like to add anything, just reply to this email - I read every response personally.</p>
${common}`;
        }
        if (kind === 'share') {
            return `<p>Hi ${esc(name)},</p>
<p>Thank you for your feedback on <strong>${esc(test)}</strong>${rating ? ` and for rating it <strong>${rating}/5</strong>` : ''}.</p>
<p>If the test helped your preparation, would you share ShyamPracticePaper with your classmates and study groups? More aspirants practising means more free material we can keep building.</p>
${common}`;
        }
        return `<p>Hi ${esc(name)},</p>
<p>I saw your feedback on <strong>${esc(test)}</strong>${rating ? ` and the <strong>${rating}/5</strong> rating you gave` : ''}. I am truly grateful that you took the time to tell us what you thought.</p>
${common}`;
    }

    document.addEventListener('click', function (e) {
        const reply = e.target.closest('.fb-reply');
        if (reply) {
            current = entries.find(x => String(x.id) === reply.dataset.id);
            if (!current) return;
            initQuill();
            $('fbReplyTo').innerHTML = `<span class="fb-avatar">${esc((current.display_name || '?')[0].toUpperCase())}</span>
                <div><strong>${esc(current.display_name)}</strong><span>${esc(current.email)}</span></div>
                <div class="ms-auto">${stars(current.rating)}</div>`;
            $('fbSubject').value = `Thank you for your feedback on ${testTitle}`;
            if (quill) quill.clipboard.dangerouslyPasteHTML(template('grateful', current));
            $('fbReplyMessage').classList.add('is-hidden');
            new bootstrap.Modal($('fbReplyModal')).show();
            log('reply opened for', current.email);
            return;
        }

        const tpl = e.target.closest('#fbTemplates [data-tpl]');
        if (tpl && current && quill) {
            quill.clipboard.dangerouslyPasteHTML(template(tpl.dataset.tpl, current));
            return;
        }

        const del = e.target.closest('.fb-del');
        if (del) {
            if (!confirm('Delete this feedback entry permanently?')) return;
            fetch('/api/feedback/delete/' + del.dataset.id, { method: 'DELETE' })
                .then(r => r.json())
                .then(d => {
                    if (!d.success) { say($('fbMessage'), d.message); return; }
                    entries = entries.filter(x => String(x.id) !== del.dataset.id);
                    render();
                    say($('fbMessage'), 'Feedback deleted.', 'success');
                });
        }
    });

    $('fbSendBtn').addEventListener('click', async function () {
        if (!current || !quill) return;
        const btn = this;
        const body = quill.root.innerHTML;
        const subject = $('fbSubject').value.trim();
        if (!subject) { say($('fbReplyMessage'), 'Enter a subject line.'); return; }
        if (!quill.getText().trim()) { say($('fbReplyMessage'), 'The message is empty.'); return; }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Sending...';
        try {
            const res = await fetch('/api/feedback/reply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: current.email, subject: subject, body: body })
            });
            const d = await res.json();
            log('send response', d);
            if (!d.success) { say($('fbReplyMessage'), d.message); return; }
            bootstrap.Modal.getInstance($('fbReplyModal')).hide();
            say($('fbMessage'), d.message, 'success');
        } catch (err) {
            say($('fbReplyMessage'), 'Could not reach the server.');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Send Message';
        }
    });

    $('fbBackToCourse').addEventListener('click', () => {
        $('fbStepContent').classList.add('is-hidden');
        $('fbStepTest').classList.add('is-hidden');
        $('fbStepList').classList.add('is-hidden');
        $('fbStepCourse').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Choose a course';
    });
    $('fbBackToContent').addEventListener('click', () => {
        $('fbStepTest').classList.add('is-hidden');
        $('fbStepList').classList.add('is-hidden');
        $('fbStepContent').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Choose the course content';
    });
    $('fbBackToTest').addEventListener('click', () => {
        $('fbStepList').classList.add('is-hidden');
        $('fbStepTest').classList.remove('is-hidden');
        $('fbHeading').textContent = 'Choose a test';
    });
    $('fbFilter').addEventListener('change', render);
    $('fbRefresh').addEventListener('click', loadEntries);

    let logCourse = '';

    async function loadLogCourses() {
        const grid = $('lgCourseGrid');
        grid.innerHTML = '<div class="fb-loading"><div class="spinner-border spinner-border-sm"></div> Loading...</div>';
        try {
            const res = await fetch('/api/student-logs/courses');
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            logsLoaded = true;
            $('lgTotals').innerHTML = `
                <div class="fb-sum"><small>Unique students (all courses)</small><strong>${data.totals.unique_students}</strong></div>
                <div class="fb-sum"><small>Total test attempts</small><strong>${data.totals.total_attempts}</strong></div>`;
            grid.innerHTML = '';
            if (!data.courses.length) {
                grid.innerHTML = '<div class="fb-loading">No test activity recorded yet.</div>';
                return;
            }
            data.courses.forEach(c => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'fb-pick';
                b.innerHTML = `<span class="fb-pick__code">${esc(c.code)}</span>
                               <span class="fb-pick__name">${esc(c.name || c.code)}</span>
                               <span class="fb-pick__big">${c.unique_students} <small>student${c.unique_students === 1 ? '' : 's'}</small></span>
                               <span class="fb-pick__meta">${c.total_attempts} attempts · ${c.tests_attempted} tests</span>`;
                b.addEventListener('click', () => pickLogCourse(c.code, c.name || c.code, c));
                grid.appendChild(b);
            });
            log('log courses loaded', data.courses.length);
        } catch (e) {
            grid.innerHTML = '<div class="alert alert-danger mb-0">Could not load student counts.</div>';
        }
    }

    async function pickLogCourse(code, name, stats) {
        logCourse = code;
        $('lgStepCourse').classList.add('is-hidden');
        $('lgStepDetail').classList.remove('is-hidden');
        $('lgCourseLabel').textContent = `${code} - ${name}`;
        $('lgSearch').value = '';
        await loadLogDetails(stats);
    }

    async function loadLogDetails(stats) {
        const body = $('lgTableBody');
        body.innerHTML = '<tr><td colspan="7" class="fb-loading">Loading students...</td></tr>';
        try {
            const res = await fetch('/api/student-logs/details?course_code=' + encodeURIComponent(logCourse));
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            logStudents = data.students;
            const attempts = logStudents.reduce((n, s) => n + (s.total_attempts || 0), 0);
            $('lgSummary').innerHTML = `
                <div class="fb-sum fb-sum--good"><small>Unique students</small><strong>${data.unique_students}</strong></div>
                <div class="fb-sum"><small>Total attempts</small><strong>${attempts}</strong></div>
                <div class="fb-sum"><small>Avg attempts / student</small><strong>${data.unique_students ? (attempts / data.unique_students).toFixed(1) : '-'}</strong></div>`;
            renderLogTable();
            log('log details loaded', data.unique_students);
        } catch (e) {
            body.innerHTML = '<tr><td colspan="7"><div class="alert alert-danger mb-0">Could not load students.</div></td></tr>';
        }
    }

    function renderLogTable() {
        const q = $('lgSearch').value.trim().toLowerCase();
        const rows = logStudents.filter(s =>
            !q || (s.username || '').toLowerCase().includes(q) || (s.email || '').toLowerCase().includes(q));
        const body = $('lgTableBody');
        $('lgEmpty').classList.toggle('is-hidden', rows.length > 0);
        body.innerHTML = rows.map((s, i) => `
            <tr>
                <td>${i + 1}</td>
                <td><span class="fb-avatar fb-avatar--sm">${esc(((s.username || s.email || '?')[0] || '?').toUpperCase())}</span> ${esc(s.username || '-')}</td>
                <td class="fb-cell-email">${esc(s.email)}</td>
                <td><span class="fb-count-pill">${s.tests_taken}</span></td>
                <td>${s.total_attempts}</td>
                <td>${esc(s.first_activity || '-')}</td>
                <td>${esc(s.last_activity || '-')}</td>
            </tr>`).join('');
    }

    $('lgBack').addEventListener('click', () => {
        $('lgStepDetail').classList.add('is-hidden');
        $('lgStepCourse').classList.remove('is-hidden');
        loadLogCourses();
    });
    $('lgSearch').addEventListener('input', renderLogTable);
    $('lgRefresh').addEventListener('click', () => loadLogDetails());

    loadCourses();
});
