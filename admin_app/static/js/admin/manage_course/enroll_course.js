document.addEventListener('DOMContentLoaded', () => {
    const canManage = (document.body.dataset.canManage || '') === '1';
    const addForm = document.getElementById('add-course-form');
    const coursesTable = document.getElementById('courses-table');
    const tbody = document.getElementById('courses-tbody');
    const searchInput = document.getElementById('course-search');
    const emptyBox = document.getElementById('mc-empty');
    const countBadge = document.getElementById('course-count');

    const editModal = document.getElementById('editModal');
    const editCode = document.getElementById('editCode');
    const editCodeView = document.getElementById('editCodeView');
    const editName = document.getElementById('editName');
    const editSubgroup = document.getElementById('editSubgroup');

    const toolbar = [
        [{ 'header': [2, 3, false] }],
        ['bold', 'italic', 'underline'],
        [{ 'list': 'ordered' }, { 'list': 'bullet' }],
        ['link', 'clean']
    ];

    let addQuill = null;
    let editQuill = null;
    if (window.Quill) {
        if (document.getElementById('addDescEditor')) {
            addQuill = new Quill('#addDescEditor', { theme: 'snow', placeholder: 'Describe this course...', modules: { toolbar } });
        }
        if (document.getElementById('editDescEditor')) {
            editQuill = new Quill('#editDescEditor', { theme: 'snow', placeholder: 'Describe this course...', modules: { toolbar } });
        }
    }

    const loginUrl = document.body.dataset.loginUrl || '/admin_login';

    function apiMessage(data, fallback) {
        return (data && (data.message || data.error)) || fallback;
    }

    function sessionLost(res, data) {
        if (res.status === 401 || (res.status === 403 && data && data.error === 'session_expired')) {
            showFlashMessage('Your session has ended. Redirecting to login...', 'error');
            setTimeout(() => { window.location.href = loginUrl; }, 1200);
            return true;
        }
        return false;
    }

    const isEmptyQuill = (q) => !q || q.getText().trim().length === 0;
    const getHtml = (q) => (q ? q.root.innerHTML : '');
    const setHtml = (q, html) => {
        if (!q) return;
        q.setContents(q.clipboard.convert(html || ''), 'silent');
        q.history.clear();
    };

    function plainText(html) {
        const doc = new DOMParser().parseFromString(html || '', 'text/html');
        return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
    }

    function shorten(text, max) {
        const t = text || '';
        return t.length > max ? t.slice(0, max - 1) + '\u2026' : t;
    }

    const confirmAction = (opts) => (window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title)));

    function showFlashMessage(message, type) {
        const tone = type === 'error' ? 'danger' : (type || 'info');
        if (window.adminToast) { window.adminToast(escapeHtml(message), tone); return; }
        const stack = document.getElementById('appFlashStack');
        if (!stack) { alert(message); return; }
        const map = { success: 'success', error: 'danger', info: 'info' };
        const el = document.createElement('div');
        el.className = `app-flash app-flash--${map[type] || 'info'}`;
        el.setAttribute('role', 'alert');
        el.innerHTML = `<i class="fas ${type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-info'} app-flash__icon"></i>
            <span class="app-flash__msg"></span>
            <button type="button" class="app-flash__close" aria-label="Close">&times;</button>`;
        el.querySelector('.app-flash__msg').textContent = message;
        stack.appendChild(el);
        requestAnimationFrame(() => el.classList.add('show'));
        const timer = setTimeout(() => dismiss(el), 5000);
        el.querySelector('.app-flash__close').addEventListener('click', () => { clearTimeout(timer); dismiss(el); });
        function dismiss(node) { node.classList.add('hide'); setTimeout(() => node.remove(), 350); }
    }

    function refreshCount() {
        populateGroupFilter();
        applyFilters();
    }

    function buildRow(course) {
        const tr = document.createElement('tr');
        tr.dataset.code = course.code;
        tr.dataset.name = course.name;
        tr.dataset.subgroup = course.subgroup || '';
        tr.dataset.description = course.description || '';
        const subCell = course.subgroup
            ? `<span class="mc-tag">${escapeHtml(course.subgroup)}</span>`
            : `<span class="mc-dash">-</span>`;
        const actions = canManage ? `
            <td data-label="Actions" class="mc-row-actions">
                <button class="mc-btn mc-btn-sm mc-btn-edit" type="button"><i class="fas fa-pen"></i> Edit</button>
                <button class="mc-btn mc-btn-sm mc-btn-danger" type="button"><i class="fas fa-trash"></i> Delete</button>
            </td>` : '';
        tr.innerHTML = `
            <td data-label="Code"><span class="mc-code">${escapeHtml(course.code)}</span></td>
            <td data-label="Group" data-field="name">${escapeHtml(course.name)}</td>
            <td data-label="Subgroup" data-field="subgroup">${subCell}</td>
            <td data-label="Description" data-field="description" class="mc-desc">${escapeHtml(plainText(course.description))}</td>
            ${actions}`;
        return tr;
    }

    function escapeHtml(str) {
        const d = document.createElement('div');
        d.textContent = str == null ? '' : String(str);
        return d.innerHTML;
    }

    const GROUP_CODES = window.MC_GROUP_CODES || {};
    const groupSelect = document.getElementById('add-name');
    const codeSelect = document.getElementById('add-code');

    function fillCodes(group) {
        if (!codeSelect) return;
        const codes = GROUP_CODES[group] || [];
        codeSelect.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.disabled = true;
        placeholder.selected = true;
        placeholder.textContent = codes.length ? '-- Select a code --' : '-- Select a group first --';
        codeSelect.appendChild(placeholder);
        codes.forEach((code) => {
            const opt = document.createElement('option');
            opt.value = code;
            opt.textContent = code;
            codeSelect.appendChild(opt);
        });
    }

    if (groupSelect) {
        groupSelect.addEventListener('change', function () { fillCodes(this.value); });
    }

    if (addForm) {
        addForm.addEventListener('reset', function () {
            setTimeout(function () { fillCodes(''); }, 0);
        });
        addForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('add-submit');
            const code = addForm.querySelector('[name="code"]').value.trim();
            const name = addForm.querySelector('[name="name"]').value.trim();
            const subgroup = addForm.querySelector('[name="subgroup"]').value.trim();

            if (!code || !name) { showFlashMessage('Course code and group name are required.', 'error'); return; }
            if (isEmptyQuill(addQuill)) { showFlashMessage('Please add a description.', 'error'); return; }
            const approved = await confirmAction({
                tone: 'primary',
                icon: 'fa-plus',
                title: `Add the course "${code}"?`,
                items: [
                    { label: 'Group', value: name },
                    { label: 'Code', value: code },
                    { label: 'Subgroup', value: subgroup || '(none)' }
                ],
                confirmText: 'Add course'
            });
            if (!approved) return;

            const payload = { code, name, subgroup, description: getHtml(addQuill) };
            btn.disabled = true;
            try {
                const res = await fetch(addForm.dataset.addUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json().catch(() => ({}));
                if (res.ok) {
                    showFlashMessage(result.message || 'Course added.', 'success');
                    if (tbody) tbody.insertBefore(buildRow(result.course || payload), tbody.firstChild);
                    bumpCatalogCount(name, code, 1);
                    addForm.reset();
                    setHtml(addQuill, '');
                    refreshCount();
                } else if (!sessionLost(res, result)) {
                    showFlashMessage(apiMessage(result, 'Could not add course.'), 'error');
                }
            } catch (err) {
                showFlashMessage('Network error. Please try again.', 'error');
            } finally {
                btn.disabled = false;
            }
        });
    }

    const clearBtn = document.getElementById('add-clear');
    if (clearBtn) clearBtn.addEventListener('click', () => { addForm.reset(); setHtml(addQuill, ''); });

    const groupFilter = document.getElementById('group-filter');
    const toggleBtn = document.getElementById('toggle-courses-btn');
    const toggleText = document.getElementById('toggle-courses-text');
    const coursesWrapper = document.getElementById('courses-wrapper');
    let sortState = { key: null, dir: 1 };

    const allRows = () => (tbody ? Array.from(tbody.querySelectorAll('tr')) : []);

    function populateGroupFilter() {
        if (!groupFilter) return;
        const current = groupFilter.value;
        const groups = [...new Set(allRows().map(r => r.dataset.name).filter(Boolean))].sort();
        groupFilter.innerHTML = '<option value="">All groups</option>' +
            groups.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
        if (groups.includes(current)) groupFilter.value = current;
    }

    function updateStats() {
        const rows = allRows();
        const groups = new Set(rows.map(r => r.dataset.name).filter(Boolean));
        const subs = new Set(rows.map(r => r.dataset.subgroup).filter(Boolean));
        const visible = rows.filter(r => r.style.display !== 'none').length;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        set('stat-courses', rows.length);
        set('stat-groups', groups.size);
        set('stat-subgroups', subs.size);
        set('stat-visible', visible);
        set('nav-count', rows.length);
        if (countBadge) countBadge.textContent = rows.length;
    }

    function applyFilters() {
        const q = searchInput ? searchInput.value.trim().toLowerCase() : '';
        const g = groupFilter ? groupFilter.value : '';
        let visible = 0;
        allRows().forEach(row => {
            const hay = `${row.dataset.code} ${row.dataset.name} ${row.dataset.subgroup}`.toLowerCase();
            const show = (!q || hay.includes(q)) && (!g || row.dataset.name === g);
            row.style.display = show ? '' : 'none';
            if (show) visible++;
        });
        if (emptyBox) emptyBox.style.display = visible === 0 ? 'flex' : 'none';
        updateStats();
    }

    function sortRows(key) {
        if (!tbody) return;
        sortState.dir = (sortState.key === key) ? -sortState.dir : 1;
        sortState.key = key;
        allRows().sort((a, b) => {
            const av = (a.dataset[key] || '').toLowerCase();
            const bv = (b.dataset[key] || '').toLowerCase();
            if (av === bv) return 0;
            return av > bv ? sortState.dir : -sortState.dir;
        }).forEach(r => tbody.appendChild(r));
        document.querySelectorAll('.mc-sortable').forEach(th => {
            const active = th.dataset.sort === key;
            th.classList.toggle('sorted', active);
            const icon = th.querySelector('i');
            if (icon) icon.className = active
                ? (sortState.dir === 1 ? 'fas fa-sort-up' : 'fas fa-sort-down')
                : 'fas fa-sort';
        });
    }

    if (searchInput) searchInput.addEventListener('input', applyFilters);
    if (groupFilter) groupFilter.addEventListener('change', applyFilters);
    document.querySelectorAll('.mc-sortable').forEach(th => {
        th.addEventListener('click', () => sortRows(th.dataset.sort));
    });

    if (toggleBtn && coursesWrapper) {
        toggleBtn.addEventListener('click', () => {
            const hidden = coursesWrapper.classList.toggle('mc-hidden');
            toggleBtn.setAttribute('aria-expanded', String(!hidden));
            if (toggleText) toggleText.textContent = hidden ? 'Show' : 'Hide';
            const icon = toggleBtn.querySelector('i');
            if (icon) icon.className = hidden ? 'fas fa-eye' : 'fas fa-eye-slash';
        });
    }

    const isMobile = () => window.matchMedia('(max-width: 991px)').matches;

    const navItems = document.querySelectorAll('.as-view[data-panel]');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const target = item.dataset.panel;
            navItems.forEach(i => i.classList.toggle('is-active', i === item));
            document.querySelectorAll('.mc-panel').forEach(p => {
                p.hidden = (p.id !== target);
            });
            history.replaceState(null, '', '#' + target);
            if (target === 'panel-list') applyFilters();
            if (isMobile() && window.asClose) window.asClose();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });

    const initialPanel = (window.location.hash || '').slice(1);
    const initialItem = initialPanel && Array.from(navItems).find(i => i.dataset.panel === initialPanel);
    if (initialItem) initialItem.click();

    const groupsPanel = document.getElementById('panel-groups');
    const groupForm = document.getElementById('group-form');
    const codeForm = document.getElementById('code-form');

    async function catalogRequest(url, method, body) {
        const res = await fetch(url, {
            method,
            headers: body ? { 'Content-Type': 'application/json' } : undefined,
            body: body ? JSON.stringify(body) : undefined
        });
        let data = {};
        try { data = await res.json(); } catch (err) {}
        if (sessionLost(res, data)) return { ok: false, message: null, redirected: true };
        return { ok: res.ok && data.success === true, message: apiMessage(data, null) };
    }

    const TOAST_KEY = 'mcPendingToast';

    function reloadOnPanel(panel, message) {
        let carried = false;
        try {
            sessionStorage.setItem(TOAST_KEY, JSON.stringify({ message, type: 'success' }));
            carried = true;
        } catch (err) {}
        if (!carried) showFlashMessage(message, 'success');
        history.replaceState(null, '', '#' + panel);
        setTimeout(() => window.location.reload(), carried ? 150 : 1600);
    }

    function showCarriedToast() {
        try {
            const raw = sessionStorage.getItem(TOAST_KEY);
            if (!raw) return;
            sessionStorage.removeItem(TOAST_KEY);
            const t = JSON.parse(raw);
            if (t && t.message) showFlashMessage(t.message, t.type || 'success');
        } catch (err) {}
    }

    function bumpCatalogCount(group, code, delta) {
        const bump = (row, btnSel) => {
            if (!row) return;
            const cell = row.querySelector('[data-field="courses"]');
            const btn = row.querySelector(btnSel);
            const next = Math.max(0, parseInt((btn && btn.dataset.used) || (cell && cell.textContent) || '0', 10) + delta);
            if (cell) cell.textContent = next;
            if (btn) btn.dataset.used = String(next);
        };
        const codesTable = document.getElementById('codes-table');
        const groupsTable = document.getElementById('groups-table');
        if (codesTable && code) bump(codesTable.querySelector(`tr[data-code="${CSS.escape(code)}"]`), '.mc-del-code');
        if (groupsTable && group) bump(groupsTable.querySelector(`tr[data-group="${CSS.escape(group)}"]`), '.mc-del-group');
    }

    if (groupForm) {
        groupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = groupForm.querySelector('[type="submit"]');
            const groupName = groupForm.querySelector('[name="group_name"]').value.trim().toUpperCase();
            const platform = (groupForm.querySelector('[name="platform"]') || {}).value || 'competitive';
            if (!groupName) { showFlashMessage('Group name is required.', 'error'); return; }
            btn.disabled = true;
            try {
                const r = await catalogRequest(groupForm.dataset.url, 'POST', { group_name: groupName, platform });
                if (r.ok) {
                    reloadOnPanel('panel-groups', `Group "${groupName}" added.`);
                    return;
                }
                if (!r.redirected) showFlashMessage(r.message || 'Could not add the group.', 'error');
            } catch (err) {
                showFlashMessage('Network error. Please try again.', 'error');
            }
            btn.disabled = false;
        });
    }

    document.querySelectorAll('.mc-group-platform').forEach((sel) => {
        sel.addEventListener('change', async () => {
            const wanted = sel.value;
            const previous = wanted === 'placement' ? 'competitive' : 'placement';
            const ok = window.adminConfirm ? await window.adminConfirm({
                tone: 'primary', title: `Move ${sel.dataset.group} to the ${wanted === 'placement' ? 'Placement Exam Portal' : 'Competitive Exam Platform'}?`,
                message: wanted === 'placement' ? 'Coding, communication and TCS content become available for this group.' : 'Only mock tests and study material stay available; coding, communication and TCS sections must already be unticked in Course Catalog.',
                confirmText: 'Change platform' }) : window.confirm('Change the platform?');
            if (!ok) { sel.value = previous; return; }
            try {
                const r = await catalogRequest(sel.dataset.url, 'PUT', { label: sel.dataset.label, position: sel.dataset.position, platform: wanted });
                if (r.ok) { showFlashMessage(`${sel.dataset.group} is now a ${wanted} group.`, 'success'); return; }
                sel.value = previous;
                if (!r.redirected) showFlashMessage(r.message || 'Could not change the platform.', 'error');
            } catch (err) {
                sel.value = previous;
                showFlashMessage('Network error. Please try again.', 'error');
            }
        });
    });

    if (codeForm) {
        codeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = codeForm.querySelector('[type="submit"]');
            const groupName = codeForm.querySelector('[name="group_name"]').value;
            const code = codeForm.querySelector('[name="code"]').value.trim().toUpperCase();
            if (!groupName) { showFlashMessage('Choose a group for this code.', 'error'); return; }
            if (!code) { showFlashMessage('Code is required.', 'error'); return; }
            btn.disabled = true;
            try {
                const r = await catalogRequest(codeForm.dataset.url, 'POST', { group_name: groupName, code });
                if (r.ok) {
                    reloadOnPanel('panel-groups', `Code "${code}" added under ${groupName}.`);
                    return;
                }
                if (!r.redirected) showFlashMessage(r.message || 'Could not add the code.', 'error');
            } catch (err) {
                showFlashMessage('Network error. Please try again.', 'error');
            }
            btn.disabled = false;
        });
    }

    if (groupsPanel) {
        groupsPanel.addEventListener('click', async (e) => {
            const delGroup = e.target.closest('.mc-del-group');
            const delCode = e.target.closest('.mc-del-code');
            if (!delGroup && !delCode) return;
            const btn = delGroup || delCode;
            const used = parseInt(btn.dataset.used || '0', 10);
            const codes = delGroup ? parseInt(btn.dataset.codes || '0', 10) : 0;
            const label = delGroup ? `group "${btn.dataset.name}"` : `code "${btn.dataset.code}"`;
            const blockers = [];
            if (used > 0) blockers.push(`${used} course(s) use this ${delGroup ? 'group' : 'code'}`);
            if (codes > 0) blockers.push(`${codes} code(s) still belong to it`);
            if (blockers.length) {
                await confirmAction({
                    tone: 'blocked',
                    title: `The ${label} can't be deleted yet`,
                    items: blockers,
                    note: delGroup
                        ? 'Delete its courses first, then its codes, then the group. Nothing was changed.'
                        : 'Delete the courses that use it first. Nothing was changed.'
                });
                return;
            }
            const approved = await confirmAction({
                tone: 'danger',
                title: delGroup ? `Delete the group "${btn.dataset.name}"?` : `Delete the code "${btn.dataset.code}" from ${btn.dataset.group}?`,
                message: delGroup
                    ? 'It will disappear from the Group dropdowns and the homepage.'
                    : 'It will disappear from the Course Code dropdown for this group.',
                note: 'This cannot be undone.',
                confirmText: delGroup ? 'Delete group' : 'Delete code'
            });
            if (!approved) return;
            const url = delGroup
                ? groupsPanel.dataset.deleteGroupUrl.replace('NAME_PLACEHOLDER', encodeURIComponent(btn.dataset.name))
                : groupsPanel.dataset.deleteCodeUrl
                    .replace('GROUP_PLACEHOLDER', encodeURIComponent(btn.dataset.group))
                    .replace('CODE_PLACEHOLDER', encodeURIComponent(btn.dataset.code));
            btn.disabled = true;
            try {
                const r = await catalogRequest(url, 'DELETE');
                if (r.ok) {
                    reloadOnPanel('panel-groups', `Deleted the ${label}.`);
                    return;
                }
                if (!r.redirected) showFlashMessage(r.message || 'Could not delete.', 'error');
            } catch (err) {
                showFlashMessage('Network error. Please try again.', 'error');
            }
            btn.disabled = false;
        });
    }

    let editBaseline = null;

    const openEdit = (row) => {
        editCode.value = row.dataset.code;
        editCodeView.value = row.dataset.code;
        editName.value = row.dataset.name || '';
        editSubgroup.value = row.dataset.subgroup || '';
        editModal.classList.add('open');
        setHtml(editQuill, row.dataset.description || '');
        editBaseline = {
            subgroup: editSubgroup.value.trim(),
            html: getHtml(editQuill),
            text: editQuill ? editQuill.getText().trim() : ''
        };
    };
    const closeEdit = () => { editModal.classList.remove('open'); editBaseline = null; };

    ['editClose', 'editCancel'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', closeEdit);
    });
    if (editModal) {
        editModal.addEventListener('click', (e) => { if (e.target === editModal) closeEdit(); });
    }
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && editModal.classList.contains('open')) closeEdit(); });

    async function deleteCourse(row, btn) {
        const code = row.dataset.code;
        btn.disabled = true;
        let usage = null;
        try {
            const res = await fetch(coursesTable.dataset.usageUrlTemplate.replace('CODE_PLACEHOLDER', encodeURIComponent(code)), {
                headers: { 'Accept': 'application/json' }
            });
            usage = await res.json().catch(() => ({}));
            if (!res.ok || typeof usage.deletable !== 'boolean') {
                if (!sessionLost(res, usage)) showFlashMessage(apiMessage(usage, 'Could not check this course. Refresh the page and try again.'), 'error');
                return;
            }
        } catch (err) {
            showFlashMessage('Network error. Please try again.', 'error');
            return;
        } finally {
            btn.disabled = false;
        }

        const describe = (list) => (list || []).map(u => (u.label === 'premium page text' ? 'Premium page text' : `${u.count} ${u.label}`));
        if (!usage.deletable) {
            await confirmAction({
                tone: 'blocked',
                title: `The course "${code}" can't be deleted`,
                message: 'Students, payments or content still depend on it:',
                items: describe(usage.blocking),
                note: 'Remove its content first. A course stays while any student is enrolled, has paid or holds a premium subscription. Nothing was changed.'
            });
            return;
        }

        const place = row.dataset.subgroup ? `${row.dataset.name} \u203a ${row.dataset.subgroup}` : row.dataset.name;
        const removes = describe(usage.removes);
        const approved = await confirmAction({
            tone: 'danger',
            title: `Delete the course "${code}"?`,
            message: `${place} will be removed from the course list and the student site.`,
            itemsTitle: removes.length ? 'Also removed with it' : '',
            items: removes,
            note: 'This cannot be undone.',
            confirmText: 'Delete course'
        });
        if (!approved) return;

        btn.disabled = true;
        try {
            const url = coursesTable.dataset.deleteUrlTemplate.replace('CODE_PLACEHOLDER', encodeURIComponent(code));
            const res = await fetch(url, { method: 'POST', headers: { 'Accept': 'application/json' } });
            const result = await res.json().catch(() => ({}));
            if (res.ok) {
                showFlashMessage(result.message || `Course "${code}" deleted.`, 'success');
                bumpCatalogCount(row.dataset.name, code, -1);
                row.remove();
                refreshCount();
            } else if (!sessionLost(res, result)) {
                showFlashMessage(apiMessage(result, 'Could not delete.'), 'error');
            }
        } catch (err) {
            showFlashMessage('Network error. Please try again.', 'error');
        } finally {
            btn.disabled = false;
        }
    }

    if (coursesTable) {
        coursesTable.addEventListener('click', (e) => {
            const row = e.target.closest('tr[data-code]');
            if (!row || !canManage) return;
            const del = e.target.closest('.mc-btn-danger');
            if (e.target.closest('.mc-btn-edit')) {
                openEdit(row);
            } else if (del && !del.disabled) {
                deleteCourse(row, del);
            }
        });
    }

    const saveBtn = document.getElementById('editSave');
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const code = editCode.value;
            const row = tbody.querySelector(`tr[data-code="${CSS.escape(code)}"]`);
            const name = (row && row.dataset.name) || editName.value.trim();
            const subgroup = editSubgroup.value.trim();
            if (!name) { showFlashMessage('Group name cannot be empty.', 'error'); return; }
            if (isEmptyQuill(editQuill)) { showFlashMessage('Description cannot be empty.', 'error'); return; }

            const description = getHtml(editQuill);
            const base = editBaseline || { subgroup: '', html: '', text: '' };
            const changes = [];
            if (subgroup !== base.subgroup) changes.push({ label: 'Subgroup', from: base.subgroup, to: subgroup });
            if (description !== base.html) {
                const nowText = editQuill.getText().trim();
                changes.push(nowText === base.text
                    ? { label: 'Description', value: 'Formatting changed' }
                    : { label: 'Description', from: shorten(base.text, 70), to: shorten(nowText, 70) });
            }
            if (!changes.length) { showFlashMessage('No changes to save.', 'info'); return; }

            const approved = await confirmAction({
                tone: 'primary',
                title: `Save changes to the course "${code}"?`,
                itemsTitle: 'What will change',
                items: changes,
                confirmText: 'Save changes'
            });
            if (!approved) return;

            const url = coursesTable.dataset.updateUrlTemplate.replace('CODE_PLACEHOLDER', encodeURIComponent(code));
            saveBtn.disabled = true;
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({ name, subgroup, description })
                });
                const result = await res.json().catch(() => ({}));
                if (res.ok) {
                    showFlashMessage(result.message || `Course "${code}" updated.`, result.status === 'success' ? 'success' : 'info');
                    if (row) {
                        row.dataset.subgroup = subgroup;
                        row.dataset.description = description;
                        row.querySelector('td[data-field="subgroup"]').innerHTML = subgroup
                            ? `<span class="mc-tag">${escapeHtml(subgroup)}</span>`
                            : `<span class="mc-dash">-</span>`;
                        row.querySelector('td[data-field="description"]').textContent = plainText(description);
                    }
                    closeEdit();
                    refreshCount();
                } else if (!sessionLost(res, result)) {
                    showFlashMessage(apiMessage(result, 'Could not save.'), 'error');
                }
            } catch (err) {
                showFlashMessage('Network error. Please try again.', 'error');
            } finally {
                saveBtn.disabled = false;
            }
        });
    }

    showCarriedToast();
    refreshCount();
});
