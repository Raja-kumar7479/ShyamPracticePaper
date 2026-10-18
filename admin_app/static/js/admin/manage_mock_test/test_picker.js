document.addEventListener('DOMContentLoaded', function () {

    const $id = (x) => document.getElementById(x);
    const select = $id('testIdSelect');
    const picker = $id('mtPicker');
    const grid = $id('mtPickerGrid');
    const search = $id('mtPickerSearch');
    const lead = $id('mtPickerLead');
    const steps = $id('mtSteps');
    const countLabel = $id('mtPickerCount');
    const pickedBar = $id('mtPickedBar');
    const pickedCourse = $id('mtPickedCourse');
    const pickedPath = $id('mtPickedPath');
    const pickedTitle = $id('mtPickedTitle');
    const pickedId = $id('mtPickedId');
    const changeBtn = $id('mtChangeTestBtn');
    if (!select || !picker || !grid) return;

    const MEMORY_KEY = 'mtPickerPlace';
    const TYPE_ORDER = ['communication_test', 'tcs_test', 'coding_test', 'mock_test', 'aptitude_test'];
    const TYPE_LABEL = {
        communication_test: { label: 'Communication tests', icon: 'fa-comments' },
        tcs_test: { label: 'TCS NQT exams', icon: 'fa-building' },
        coding_test: { label: 'Coding tests', icon: 'fa-code' },
        mock_test: { label: 'Mock tests', icon: 'fa-file-pen' },
        aptitude_test: { label: 'Aptitude tests', icon: 'fa-brain' }
    };
    const typeRank = (sec) => { const i = TYPE_ORDER.indexOf(sec); return i === -1 ? TYPE_ORDER.length : i; };
    const typeLabel = (sec) => (TYPE_LABEL[sec] || { label: (sec || 'Other').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()), icon: 'fa-folder' });
    let items = [];
    let stage = 'group';
    let group = '';
    let course = '';

    function esc(v) {
        const d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }

    const groupOf = (i) => (i.course_name || 'Other').trim() || 'Other';
    const codeOf = (i) => (i.code || 'Other').trim() || 'Other';
    const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

    function remember() {
        try { sessionStorage.setItem(MEMORY_KEY, JSON.stringify({ group, course })); } catch (err) {}
    }

    function recall() {
        try {
            const saved = JSON.parse(sessionStorage.getItem(MEMORY_KEY) || 'null');
            if (!saved) return;
            if (saved.group && items.some(i => groupOf(i) === saved.group)) {
                group = saved.group;
                stage = 'course';
                if (saved.course && items.some(i => groupOf(i) === group && codeOf(i) === saved.course)) {
                    course = saved.course;
                    stage = 'content';
                }
            }
        } catch (err) {}
    }

    function paintSteps() {
        const order = ['group', 'course', 'content'];
        const current = stage === 'search' ? 'content' : stage;
        steps.querySelectorAll('.mt-step').forEach(li => {
            const idx = order.indexOf(li.dataset.stage);
            const done = idx < order.indexOf(current);
            li.classList.toggle('is-active', li.dataset.stage === current);
            li.classList.toggle('is-done', done);
            const text = li.querySelector('.mt-step__text');
            if (li.dataset.stage === 'group') text.textContent = done && group ? group : 'Course group';
            if (li.dataset.stage === 'course') text.textContent = done && course ? course : 'Course';
            if (li.dataset.stage === 'content') text.textContent = 'Test content';
        });
        if (stage === 'group') lead.textContent = 'Choose the course group, for example GATE.';
        else if (stage === 'course') lead.textContent = `Choose the course inside ${group}.`;
        else if (stage === 'content') lead.textContent = `Choose the test content in ${group} › ${course}. Each card holds its own test descriptions.`;
        else lead.textContent = 'Search results across every course. Clear the search to go back.';
    }

    function groupTiles() {
        const by = {};
        items.forEach(i => {
            const g = groupOf(i);
            if (!by[g]) by[g] = { courses: new Set(), contents: 0, tests: 0 };
            by[g].courses.add(codeOf(i));
            by[g].contents++;
            by[g].tests += Number(i.description_count || 0);
        });
        const names = Object.keys(by).sort();
        countLabel.textContent = `${plural(names.length, 'course group')}`;
        if (!names.length) return '<div class="mt-picker__loading">No test content exists yet. Add a Mock Test, Communication or Coding block in Course Content first.</div>';
        return names.map(g => `
            <button type="button" class="mt-tcard mt-tcard--group" data-group="${esc(g)}">
                <span class="mt-tcard__icon"><i class="fas fa-layer-group"></i></span>
                <span class="mt-tcard__title">${esc(g)}</span>
                <span class="mt-tcard__meta">${plural(by[g].courses.size, 'course')} · ${plural(by[g].contents, 'test content')} · ${plural(by[g].tests, 'test')}</span>
                <span class="mt-tcard__go">Open <i class="fas fa-arrow-right"></i></span>
            </button>`).join('');
    }

    function courseTiles() {
        const by = {};
        items.filter(i => groupOf(i) === group).forEach(i => {
            const c = codeOf(i);
            if (!by[c]) by[c] = { sub: i.course_subgroup || '', contents: 0, tests: 0 };
            by[c].contents++;
            by[c].tests += Number(i.description_count || 0);
        });
        const codes = Object.keys(by).sort();
        countLabel.textContent = `${plural(codes.length, 'course')} in ${group}`;
        return codes.map(c => `
            <button type="button" class="mt-tcard mt-tcard--course" data-course="${esc(c)}">
                <span class="mt-tcard__top"><span class="mt-badge mt-badge--course">${esc(c)}</span><span class="mt-badge mt-badge--group">${esc(group)}</span></span>
                <span class="mt-tcard__title">${esc(by[c].sub || c)}</span>
                <span class="mt-tcard__meta">${plural(by[c].contents, 'test content')} · ${plural(by[c].tests, 'test')}</span>
                <span class="mt-tcard__go">Open <i class="fas fa-arrow-right"></i></span>
            </button>`).join('');
    }

    function contentCard(i, showPath) {
        const n = Number(i.description_count || 0);
        const planned = Number(i.declared_questions || 0);
        const labelCls = (i.label || '').toLowerCase() === 'paid' ? 'mt-badge--paid' : 'mt-badge--free';
        const isPicked = select.value === i.test_id;
        return `
            <button type="button" class="mt-tcard${isPicked ? ' is-picked' : ''}" data-id="${esc(i.test_id)}">
                <span class="mt-tcard__top">
                    ${showPath ? `<span class="mt-badge mt-badge--group">${esc(groupOf(i))}</span>` : ''}
                    <span class="mt-badge mt-badge--course">${esc(codeOf(i))}</span>
                    <span class="mt-badge ${labelCls}">${esc(i.label || '')}</span>
                </span>
                <span class="mt-tcard__title">${esc(i.title)}</span>
                ${i.subtitle ? `<span class="mt-tcard__sub">${esc(i.subtitle)}</span>` : ''}
                <span class="mt-id-row">
                    <code class="mt-id">${esc(i.test_id)}</code>
                    <span class="mt-copy" data-copy="${esc(i.test_id)}" title="Copy section ID"><i class="far fa-copy"></i></span>
                </span>
                <span class="mt-tcard__meta">${n === 0 ? 'No test description yet - add the first one' : `${plural(n, 'test description')} · ${planned} questions planned`}</span>
            </button>`;
    }

    function groupedCards(rows, showPath) {
        const byType = {};
        rows.forEach(i => { (byType[i.section || 'other'] = byType[i.section || 'other'] || []).push(i); });
        const types = Object.keys(byType).sort((a, b) => typeRank(a) - typeRank(b) || a.localeCompare(b));
        return types.map(t => {
            const meta = typeLabel(t);
            return `<div class="mt-group-head"><i class="fas ${meta.icon}"></i> ${esc(meta.label)} <span class="mt-group-head__count">${byType[t].length}</span></div>` +
                   byType[t].map(i => contentCard(i, showPath)).join('');
        }).join('');
    }

    function contentCards() {
        const rows = items.filter(i => groupOf(i) === group && codeOf(i) === course);
        countLabel.textContent = `${plural(rows.length, 'test content')} in ${group} › ${course}`;
        if (!rows.length) return '<div class="mt-picker__loading">No test content in this course yet. Add one in Course Content first.</div>';
        return groupedCards(rows, false);
    }

    function matches(item, q) {
        return [item.title, item.subtitle, item.test_id, item.code, item.course_name, item.course_subgroup, item.label]
            .some(v => (v || '').toLowerCase().includes(q));
    }

    function searchCards(q) {
        const rows = items.filter(i => matches(i, q));
        countLabel.textContent = `${rows.length} of ${items.length} test contents match`;
        if (!rows.length) return '<div class="mt-picker__loading">No test content matches your search.</div>';
        return groupedCards(rows, true);
    }

    function render() {
        const q = (search.value || '').trim().toLowerCase();
        if (q) {
            stage = 'search';
        } else if (stage === 'search') {
            stage = course ? 'content' : (group ? 'course' : 'group');
        }
        paintSteps();
        if (stage === 'search') grid.innerHTML = searchCards(q);
        else if (stage === 'group') grid.innerHTML = groupTiles();
        else if (stage === 'course') grid.innerHTML = courseTiles();
        else grid.innerHTML = contentCards();
    }

    function goTo(next) {
        if (next === 'group') { group = ''; course = ''; }
        if (next === 'course') { course = ''; }
        stage = next;
        search.value = '';
        remember();
        render();
    }

    function pick(item) {
        group = groupOf(item);
        course = codeOf(item);
        stage = 'content';
        remember();
        select.value = item.test_id;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        pickedCourse.textContent = course;
        pickedPath.textContent = `${group} › ${course}${item.course_subgroup ? ' · ' + item.course_subgroup : ''}`;
        pickedTitle.textContent = item.title;
        pickedId.textContent = item.test_id;
        pickedBar.classList.remove('is-hidden');
        picker.classList.add('is-hidden');
        console.log('[TESTS] picked', item.test_id, 'in', group, course);
    }

    function load(list) {
        items = list || [];
        const wanted = new URLSearchParams(window.location.search).get('group');
        if (wanted && items.some(i => groupOf(i) === wanted.toUpperCase())) {
            group = wanted.toUpperCase();
            course = '';
            stage = 'course';
            remember();
            history.replaceState(null, '', window.location.pathname);
        } else if (stage === 'group' && !group) {
            recall();
        }
        render();
    }

    document.addEventListener('mt-content-loaded', function (e) { load(e.detail); });
    if (Array.isArray(window.MT_CONTENT) && window.MT_CONTENT.length && !items.length) load(window.MT_CONTENT);

    search.addEventListener('input', render);

    steps.addEventListener('click', function (e) {
        const li = e.target.closest('.mt-step');
        if (!li || !li.classList.contains('is-done')) return;
        goTo(li.dataset.stage);
    });

    grid.addEventListener('click', function (e) {
        const copy = e.target.closest('.mt-copy');
        if (copy) {
            e.stopPropagation();
            navigator.clipboard.writeText(copy.dataset.copy).then(() => {
                copy.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => { copy.innerHTML = '<i class="far fa-copy"></i>'; }, 1200);
            });
            return;
        }
        const gTile = e.target.closest('.mt-tcard--group');
        if (gTile) { group = gTile.dataset.group; course = ''; goTo('course'); return; }
        const cTile = e.target.closest('.mt-tcard--course');
        if (cTile) { course = cTile.dataset.course; goTo('content'); return; }
        const card = e.target.closest('.mt-tcard[data-id]');
        if (!card) return;
        const item = items.find(i => i.test_id === card.dataset.id);
        if (item) pick(item);
    });

    changeBtn.addEventListener('click', function () {
        picker.classList.remove('is-hidden');
        pickedBar.classList.add('is-hidden');
        stage = course ? 'content' : 'group';
        search.value = '';
        render();
        picker.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
});
