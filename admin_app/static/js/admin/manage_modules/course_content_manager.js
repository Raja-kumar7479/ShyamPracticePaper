document.addEventListener('DOMContentLoaded', function () {

    const CAN_MANAGE = document.body.dataset.canManage === '1';
    const $ = (id) => document.getElementById(id);
    const log = (msg, extra) => console.log('[CONTENT] ' + msg, extra === undefined ? '' : extra);

    const navItems = document.querySelectorAll('.as-view[data-view]');
    const views = { add: $('view-add'), all: $('view-all') };

    const stepPick = $('ccStepPick');
    const stepList = $('ccStepList');
    const courseGrid = $('ccCourseGrid');
    const labelGrid = $('ccLabelGrid');
    const backBtn = $('ccBack');
    const listTitle = $('ccListTitle');
    const listSub = $('ccListSub');

    const cardsWrap = $('ccCards');
    const spinner = $('ccSpinner');
    const emptyBox = $('ccEmpty');
    const navCount = $('ccNavCount');
    const searchInput = $('ccSearch');
    const labelFilter = $('ccLabelFilter');
    const refreshBtn = $('ccRefresh');

    const imageModal = $('imageModal');
    const modalImage = $('modalImage');
    const newImageFile = $('newImageFile');
    const detailsModal = $('detailsModal');
    const detailsModalTitle = $('detailsModalTitle');
    const detailsModalBody = $('detailsModalBody');

    let allContent = [];
    let loaded = false;
    let currentImageId = null;
    let pickedCourse = '';
    let pickedLabel = '';

    function esc(value) {
        const d = document.createElement('div');
        d.appendChild(document.createTextNode(value == null ? '' : String(value)));
        return d.innerHTML;
    }

    function money(value) {
        return '₹' + Number(value || 0).toFixed(2);
    }

    function closeSidebar() {
        if (window.matchMedia('(max-width: 991px)').matches && window.asClose) {
            window.asClose();
        }
    }

    navItems.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const target = btn.dataset.view;
            log('switching view -> ' + target);
            navItems.forEach(b => b.classList.toggle('is-active', b === btn));
            Object.keys(views).forEach(k => {
                if (views[k]) views[k].classList.toggle('is-active', k === target);
            });
            closeSidebar();
            window.scrollTo({ top: 0, behavior: 'smooth' });
            if (target === 'all') {
                showPicker();
                if (!loaded) loadContent();
            }
        });
    });

    function makeEditor(holderSel, toolbarSel, placeholder) {
        if (!window.Quill || !document.querySelector(holderSel)) return null;
        const editor = new Quill(holderSel, {
            theme: 'snow',
            placeholder: placeholder,
            modules: {
                table: true,
                toolbar: {
                    container: toolbarSel,
                    handlers: {
                        image: function () { pickAndUploadImage(editor); },
                        'cc-table': function () { insertTable(editor); },
                        'cc-premium': function () { insertPremiumMarker(editor); }
                    }
                }
            }
        });
        return editor;
    }

    function syncPremiumButton(toolbarSel, labelValue) {
        const btn = document.querySelector(toolbarSel + ' .ql-cc-premium');
        if (!btn) return;
        const free = (labelValue || 'Free') !== 'Paid';
        btn.disabled = !free;
        btn.classList.toggle('is-off', !free);
        btn.title = free ? 'Insert a link to the premium page'
                         : 'Only Free content can carry a premium link';
    }

    function insertPremiumMarker(editor) {
        const range = editor.getSelection(true) || { index: editor.getLength() - 1, length: 0 };
        editor.insertText(range.index, '[[PREMIUM]]', 'user');
        editor.setSelection(range.index + 11, 0);
        log('premium link marker inserted');
    }

    function pickAndUploadImage(editor) {
        const picker = document.createElement('input');
        picker.type = 'file';
        picker.accept = 'image/*';
        picker.addEventListener('change', function () {
            const file = this.files && this.files[0];
            if (!file) return;
            const fd = new FormData();
            fd.append('file', file);
            fetch('/upload_editor_image', { method: 'POST', body: fd })
                .then(r => r.json())
                .then(function (data) {
                    if (!data.success || !data.url) {
                        alert(data.message || 'Could not upload that image.');
                        return;
                    }
                    const range = editor.getSelection(true);
                    editor.insertEmbed(range ? range.index : editor.getLength(), 'image', data.url, 'user');
                    editor.setSelection((range ? range.index : editor.getLength()) + 1, 0);
                })
                .catch(function (e) {
                    console.error('[CONTENT] editor image upload failed:', e);
                    alert('Server error while uploading the image.');
                });
        });
        picker.click();
    }

    function insertTable(editor) {
        const table = editor.getModule('table');
        if (!table) { alert('Tables are not available in this editor.'); return; }
        const rows = parseInt(prompt('How many rows?', '3'), 10);
        if (!(rows > 0)) return;
        const cols = parseInt(prompt('How many columns?', '3'), 10);
        if (!(cols > 0)) return;
        editor.focus();
        if (!editor.getSelection()) editor.setSelection(editor.getLength(), 0);
        table.insertTable(Math.min(rows, 20), Math.min(cols, 10));
    }

    const detailsInput = $('details');
    const quill = makeEditor('#ccEditor', '#ccEditorToolbar', 'Describe this content for students...');
    if (quill) {
        quill.on('text-change', function () {
            detailsInput.value = quill.getLength() > 1 ? quill.root.innerHTML : '';
        });
    }

    const addCourseSelect = $('addCourseCode');
    const courseNameInput = $('name');
    const remainingFields = $('remainingFields');
    const labelSelect = $('label');
    const priceInput = $('price');
    const discountInput = $('discount');
    const addForm = $('addContentForm');
    const pricePreview = $('ccPricePreview');
    const previewOld = $('ccPreviewOld');
    const previewNew = $('ccPreviewNew');
    const previewSave = $('ccPreviewSave');

    function refreshPricePreview() {
        if (!pricePreview) return;
        const price = parseFloat(priceInput.value) || 0;
        const discount = parseFloat(discountInput.value) || 0;
        if (labelSelect.value !== 'Paid' || price <= 0) {
            pricePreview.classList.add('cc-hidden');
            return;
        }
        pricePreview.classList.remove('cc-hidden');
        if (discount > 0 && discount < 100) {
            const saved = Math.round(price * discount) / 100;
            previewOld.textContent = money(price);
            previewOld.style.display = '';
            previewNew.textContent = money(price - saved);
            previewSave.textContent = 'saves ' + money(saved) + ' (' + discount + '%)';
        } else {
            previewOld.style.display = 'none';
            previewNew.textContent = money(price);
            previewSave.textContent = '';
        }
    }

    const sectionSelect = $('section');
    const sectionHelp = $('sectionHelp');
    const GROUP_SECTIONS = window.CC_GROUP_SECTIONS || {};

    function fillSections(group) {
        if (!sectionSelect) return;
        const options = GROUP_SECTIONS[group] || [];
        sectionSelect.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.disabled = true;
        placeholder.selected = true;
        placeholder.textContent = options.length ? '-- Select Section --' : '-- Select a course first --';
        sectionSelect.appendChild(placeholder);
        options.forEach(function (item) {
            const opt = document.createElement('option');
            opt.value = item.value;
            opt.textContent = item.label + (item.available ? '' : ' (portal coming soon)');
            opt.dataset.help = item.help || '';
            opt.dataset.available = item.available ? '1' : '0';
            sectionSelect.appendChild(opt);
        });
        showSectionHelp();
    }

    function showSectionHelp() {
        if (!sectionHelp || !sectionSelect) return;
        const opt = sectionSelect.options[sectionSelect.selectedIndex];
        const help = opt && opt.dataset ? opt.dataset.help : '';
        sectionHelp.textContent = help ||
            'The section decides which portal this content opens for the student.';
        sectionHelp.classList.toggle('cc-hint--warn',
            !!(opt && opt.dataset && opt.dataset.available === '0'));
    }

    if (sectionSelect) sectionSelect.addEventListener('change', showSectionHelp);

    if (addCourseSelect) {
        addCourseSelect.addEventListener('change', function () {
            const opt = this.options[this.selectedIndex];
            courseNameInput.value = opt ? (opt.dataset.name || '') : '';
            fillSections(opt ? (opt.dataset.name || '') : '');
            remainingFields.classList.toggle('cc-hidden', !this.value);
        });
    }

    if (labelSelect) {
        syncPremiumButton('#ccEditorToolbar', labelSelect.value);
        labelSelect.addEventListener('change', function () {
            const paid = this.value === 'Paid';
            syncPremiumButton('#ccEditorToolbar', this.value);
            priceInput.disabled = !paid;
            if (discountInput) discountInput.disabled = !paid;
            if (!paid) {
                priceInput.value = '0.00';
                if (discountInput) discountInput.value = '0';
            }
            refreshPricePreview();
        });
    }
    if (priceInput) priceInput.addEventListener('input', refreshPricePreview);
    if (discountInput) discountInput.addEventListener('input', refreshPricePreview);

    if (addForm) {
        addForm.addEventListener('submit', function () {
            if (quill) detailsInput.value = quill.getLength() > 1 ? quill.root.innerHTML : '';
            if (priceInput.disabled) priceInput.value = '0.00';
            if (discountInput && discountInput.disabled) discountInput.value = '0';
        });
        addForm.addEventListener('reset', function () {
            setTimeout(function () {
                if (quill) quill.setText('');
                detailsInput.value = '';
                fillSections('');
                remainingFields.classList.add('cc-hidden');
                priceInput.disabled = true;
                if (discountInput) discountInput.disabled = true;
                refreshPricePreview();
            }, 0);
        });
    }

    async function loadContent() {
        if (spinner) spinner.style.display = 'block';
        try {
            log('fetching /get_all_content');
            const res = await fetch('/get_all_content');
            log('response status ' + res.status);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            allContent = Array.isArray(data) ? data : [];
            loaded = true;
            log('loaded ' + allContent.length + ' rows');
            if (navCount) navCount.textContent = allContent.length;
            paintCounts();
            if (!stepList.classList.contains('cc-hidden')) render();
        } catch (err) {
            console.error('[CONTENT] load failed:', err);
            if (emptyBox) {
                emptyBox.classList.remove('cc-hidden');
                emptyBox.querySelector('p').textContent = 'Could not load content. Please refresh.';
            }
        } finally {
            if (spinner) spinner.style.display = 'none';
        }
    }

    function paintCounts() {
        document.querySelectorAll('[data-count-for]').forEach(function (el) {
            const code = el.getAttribute('data-count-for');
            const n = allContent.filter(r => r.code === code).length;
            el.textContent = n + (n === 1 ? ' item' : ' items');
        });
        paintLabelCounts();
    }

    function paintLabelCounts() {
        document.querySelectorAll('[data-count-label]').forEach(function (el) {
            const label = el.getAttribute('data-count-label');
            const n = allContent.filter(function (r) {
                if (pickedCourse && r.code !== pickedCourse) return false;
                return !label || r.label === label;
            }).length;
            el.textContent = n + (n === 1 ? ' item' : ' items');
        });
    }

    function showPicker() {
        pickedCourse = '';
        pickedLabel = '';
        stepPick.classList.remove('cc-hidden');
        stepList.classList.add('cc-hidden');
        const cv = $('ccComboValue');
        if (cv) {
            cv.textContent = 'Search or select a course';
            cv.classList.remove('is-set');
        }
        courseGrid.querySelectorAll('.cc-pick').forEach(b => b.classList.remove('is-active'));
        labelGrid.querySelectorAll('.cc-pick').forEach(function (b) {
            b.classList.remove('is-active');
            b.disabled = true;
        });
        paintLabelCounts();
    }

    function selectCourse(code, name) {
        pickedCourse = code;
        log('course picked: ' + pickedCourse);
        if (courseGrid) {
            courseGrid.querySelectorAll('.cc-pick').forEach(function (b) {
                b.classList.toggle('is-active', b.dataset.course === code);
            });
        }
        if (comboValue) {
            comboValue.textContent = name ? (code + ' - ' + name) : code;
            comboValue.classList.add('is-set');
        }
        labelGrid.querySelectorAll('.cc-pick').forEach(b => { b.disabled = false; });
        paintLabelCounts();
        labelGrid.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    if (courseGrid) {
        courseGrid.addEventListener('click', function (e) {
            const btn = e.target.closest('.cc-pick');
            if (!btn) return;
            const nameEl = btn.querySelector('.cc-pick__name');
            selectCourse(btn.dataset.course, nameEl ? nameEl.textContent : '');
        });
    }

    const combo = $('ccCourseCombo');
    const comboToggle = $('ccComboToggle');
    const comboPanel = $('ccComboPanel');
    const comboSearch = $('ccComboSearch');
    const comboValue = $('ccComboValue');
    const comboEmpty = $('ccComboEmpty');

    function openCombo(open) {
        if (!combo) return;
        combo.classList.toggle('is-open', open);
        comboToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            comboSearch.value = '';
            filterCombo('');
            comboSearch.focus();
        }
    }

    function filterCombo(query) {
        if (!comboPanel) return;
        const q = (query || '').trim().toLowerCase();
        let shown = 0;
        comboPanel.querySelectorAll('.cc-combo__opt').forEach(function (opt) {
            const hay = (opt.dataset.course + ' ' + (opt.dataset.name || '')).toLowerCase();
            const match = !q || hay.indexOf(q) !== -1;
            opt.parentElement.classList.toggle('is-hidden', !match);
            if (match) shown++;
        });
        if (comboEmpty) comboEmpty.classList.toggle('is-hidden', shown > 0);
    }

    if (comboToggle) {
        comboToggle.addEventListener('click', function () {
            openCombo(!combo.classList.contains('is-open'));
        });
    }
    if (comboSearch) {
        comboSearch.addEventListener('input', function () { filterCombo(this.value); });
        comboSearch.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { openCombo(false); comboToggle.focus(); }
            if (e.key === 'Enter') {
                e.preventDefault();
                const first = comboPanel.querySelector('li:not(.is-hidden) .cc-combo__opt');
                if (first) first.click();
            }
        });
    }
    if (comboPanel) {
        comboPanel.addEventListener('click', function (e) {
            const opt = e.target.closest('.cc-combo__opt');
            if (!opt) return;
            selectCourse(opt.dataset.course, opt.dataset.name || '');
            openCombo(false);
        });
    }
    document.addEventListener('click', function (e) {
        if (combo && combo.classList.contains('is-open') && !combo.contains(e.target)) {
            openCombo(false);
        }
    });

    if (labelGrid) {
        labelGrid.addEventListener('click', function (e) {
            const btn = e.target.closest('.cc-pick');
            if (!btn || btn.disabled) return;
            pickedLabel = btn.dataset.label || '';
            log('label picked: ' + (pickedLabel || 'ALL'));
            openList();
        });
    }

    function openList() {
        stepPick.classList.add('cc-hidden');
        stepList.classList.remove('cc-hidden');
        if (labelFilter) labelFilter.value = pickedLabel;
        if (searchInput) searchInput.value = '';
        const courseBtn = courseGrid.querySelector('.cc-pick[data-course="' + pickedCourse + '"]');
        const courseName = courseBtn ? courseBtn.querySelector('.cc-pick__name').textContent : pickedCourse;
        listTitle.textContent = pickedCourse + '-' + courseName;
        listSub.textContent = (pickedLabel || 'All') + ' content in this course';
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    if (backBtn) backBtn.addEventListener('click', showPicker);

    function currentRows() {
        const q = (searchInput && searchInput.value || '').trim().toLowerCase();
        const label = labelFilter ? labelFilter.value : pickedLabel;
        return allContent.filter(function (row) {
            if (pickedCourse && row.code !== pickedCourse) return false;
            if (label && row.label !== label) return false;
            if (!q) return true;
            const hay = [row.title, row.subtitle, row.section, row.section_id, row.stream]
                .map(v => (v == null ? '' : String(v).toLowerCase())).join(' ');
            return hay.includes(q);
        });
    }

    function render() {
        const rows = currentRows();
        log('rendering ' + rows.length + ' card(s) for course=' + pickedCourse + ' label=' + (pickedLabel || 'ALL'));
        cardsWrap.innerHTML = '';
        if (!rows.length) {
            emptyBox.classList.remove('cc-hidden');
            emptyBox.querySelector('p').textContent = 'No content matches your filters.';
            return;
        }
        emptyBox.classList.add('cc-hidden');
        const frag = document.createDocumentFragment();
        rows.forEach(r => frag.appendChild(buildCard(r)));
        cardsWrap.appendChild(frag);
    }

    function metaRow(label, value, opts) {
        opts = opts || {};
        const dd = opts.editable && CAN_MANAGE
            ? '<dd class="editable" data-field="' + opts.field + '" data-type="' + (opts.type || 'text') + '">' + value + '</dd>'
            : '<dd>' + value + '</dd>';
        return '<dt>' + esc(label) + '</dt>' + dd;
    }

    function testLimitText(row) {
        const used = Number(row.description_count || 0);
        if (!row.max_test_descriptions) return used + ' added, no limit';
        const cap = Number(row.max_test_descriptions);
        const state = used >= cap ? ' <span class="cc-limit-full">limit reached</span>' : '';
        return used + ' of ' + cap + ' used' + state;
    }

    function priceBlock(row) {
        if (row.label !== 'Paid') return '<span class="cc-free-tag">Free</span>';
        const discount = Number(row.discount || 0);
        if (discount > 0) {
            return '<span class="cc-price-old">' + money(row.price) + '</span>' +
                   '<span class="cc-price-new">' + money(row.final_price) + '</span>' +
                   '<span class="cc-price-save">save ' + money(row.amount_saved) + '</span>';
        }
        return '<span class="cc-price-new">' + money(row.price) + '</span>';
    }

    function buildCard(row) {
        const card = document.createElement('article');
        card.className = 'cc-item' + (row.status === 'inactive' ? ' is-inactive' : '');
        card.dataset.id = row.id;

        const imgSrc = row.image_url ? '/static/' + row.image_url : '';
        const discount = Number(row.discount || 0);

        const chips = [
            '<span class="chip chip--code">' + esc(row.code) + '</span>',
            row.label === 'Paid' ? '<span class="chip chip--paid">PAID</span>'
                                 : '<span class="chip chip--free">FREE</span>',
            discount > 0 ? '<span class="chip chip--off">' + discount + '% OFF</span>' : '',
            row.status === 'inactive' ? '<span class="chip chip--inactive">INACTIVE</span>' : '',
            row.status === 'inactive' ? '<span class="chip chip--expired">HIDDEN</span>' : ''
        ].join('');

        const cover = imgSrc
            ? '<img src="' + esc(imgSrc) + '" alt="" loading="lazy">'
            : '<div class="cc-noimg"><i class="fas fa-image"></i></div>';

        const meta = [
            metaRow('Course', esc(row.course_name || row.name || '-')),
            metaRow('Stream', esc(row.stream || '-'), { editable: true, field: 'stream' }),
            metaRow('Section', esc(row.section || '-')),
            metaRow('Section ID', esc(row.section_id || '-')),
            metaRow('Price', money(row.price), { editable: row.label === 'Paid', field: 'price', type: 'number' }),
            metaRow('Discount', discount + '%', { editable: row.label === 'Paid', field: 'discount', type: 'number' }),
            metaRow('Label', esc(row.label), { editable: true, field: 'label', type: 'label' }),
            metaRow('Status', esc(row.status), { editable: true, field: 'status', type: 'status' }),
            metaRow('Test limit', testLimitText(row)),
            metaRow('Premium link in details', String(row.details || '').indexOf('[[PREMIUM]]') >= 0
                ? 'Placed' : 'Not placed'),
            metaRow('Syllabus', row.syllabus_url
                ? '<a href="/static/' + esc(String(row.syllabus_url).replace(/^\/static\//, '')) + '" target="_blank" rel="noopener">PDF</a> ('
                  + esc(row.syllabus_position === 'above' ? 'above' : 'below') + ' the description)'
                : 'None'),
            metaRow('Created', esc(row.created_at || '-')),
            metaRow('ID', esc(row.id))
        ].join('');

        const hasDetails = row.details && String(row.details).trim().length > 0;

        card.innerHTML =
            '<div class="cc-item__cover">' + cover +
                '<div class="cc-item__chips">' + chips + '</div>' +
            '</div>' +
            '<div class="cc-item__body">' +
                '<h3 class="cc-item__title">' + esc(row.title) + '</h3>' +
                '<p class="cc-item__sub">' + esc(row.subtitle || 'No subtitle') + '</p>' +
                '<div class="cc-pricing">' + priceBlock(row) + '</div>' +
                '<dl class="cc-meta">' + meta + '</dl>' +
                '<div class="cc-item__details ' + (hasDetails ? '' : 'is-empty') + '">' +
                    (hasDetails ? row.details : 'No details added.') + '</div>' +
                (hasDetails ? '<button type="button" class="cc-more-btn" data-more>Read full details</button>' : '') +
            '</div>' +
            '<div class="cc-item__foot">' +
                '<button type="button" class="btn btn-outline-secondary" data-img><i class="fas fa-image"></i> Image</button>' +
                (CAN_MANAGE ? '<button type="button" class="btn btn-brand" data-edit><i class="fas fa-pen"></i> Edit</button>' : '') +
                (CAN_MANAGE ? '<button type="button" class="btn btn-outline-danger cc-spacer" data-del><i class="fas fa-trash"></i> Delete</button>' : '') +
            '</div>';

        const detailsBox = card.querySelector('.cc-item__details');
        requestAnimationFrame(function () {
            if (detailsBox.scrollHeight > detailsBox.clientHeight + 4) detailsBox.classList.add('has-more');
        });

        const moreBtn = card.querySelector('[data-more]');
        if (moreBtn) {
            moreBtn.addEventListener('click', function () {
                detailsModalTitle.textContent = row.title || 'Details';
                detailsModalBody.innerHTML = row.details || '';
                detailsModal.classList.add('is-open');
            });
        }

        card.querySelector('[data-img]').addEventListener('click', function () {
            currentImageId = row.id;
            modalImage.src = imgSrc || '';
            modalImage.style.display = imgSrc ? 'block' : 'none';
            imageModal.classList.add('is-open');
        });

        const delBtn = card.querySelector('[data-del]');
        if (delBtn) delBtn.addEventListener('click', function () { deleteContent(row); });

        const editBtn = card.querySelector('[data-edit]');
        if (editBtn) editBtn.addEventListener('click', function () { openEdit(row); });

        card.querySelectorAll('.cc-meta dd.editable').forEach(function (cell) {
            cell.addEventListener('click', function () { beginEdit(cell, row); });
        });

        return card;
    }

    function beginEdit(cell, row) {
        if (cell.querySelector('input, select')) return;

        const field = cell.dataset.field;
        const type = cell.dataset.type;
        const original = cell.innerHTML;
        let input;

        if (type === 'label' || type === 'status') {
            input = document.createElement('select');
            (type === 'label' ? ['Free', 'Paid'] : ['active', 'inactive']).forEach(function (o) {
                const el = document.createElement('option');
                el.value = o;
                el.textContent = o;
                if (String(row[field]) === o) el.selected = true;
                input.appendChild(el);
            });
        } else {
            input = document.createElement('input');
            input.type = type === 'number' ? 'number' : 'text';
            if (type === 'number') input.step = '0.01';
            input.value = row[field] == null ? '' : row[field];
        }

        cell.innerHTML = '';
        cell.appendChild(input);
        input.focus();

        let done = false;
        const finish = async function (save) {
            if (done) return;
            done = true;
            const value = input.value;
            if (!save || String(value) === String(row[field] == null ? '' : row[field])) {
                cell.innerHTML = original;
                return;
            }
            const payload = { field: field, value: value };
            if (field === 'label' && value === 'Paid' && !(Number(row.price) > 0)) {
                const entered = prompt('This content is now Paid. Enter its price in \u20B9 (more than 0):', '');
                if (entered === null) { cell.innerHTML = original; return; }
                const price = parseFloat(entered);
                if (!(price > 0)) { alert('Paid content needs a price greater than 0.'); cell.innerHTML = original; return; }
                payload.price = price;
                const disc = prompt('Discount % (optional - leave blank for none):', '');
                if (disc !== null && disc.trim() !== '') {
                    const d = parseFloat(disc);
                    if (!(d >= 0 && d < 100)) { alert('Discount must be between 0 and 99.'); cell.innerHTML = original; return; }
                    payload.discount = d;
                }
            }
            try {
                log('updating id=' + row.id + ' field=' + field);
                const res = await fetch('/update_content_field/' + row.id, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                log('update response', data);
                if (!data.success) {
                    alert(data.message || 'Update failed.');
                    cell.innerHTML = original;
                    return;
                }
                row[field] = data.updated_field_value;
                if (data.new_price !== undefined) row.price = data.new_price;
                if (data.new_discount !== undefined) row.discount = data.new_discount;
                if (data.new_final_price !== undefined) row.final_price = data.new_final_price;
                if (data.new_amount_saved !== undefined) row.amount_saved = data.new_amount_saved;
                const idx = allContent.findIndex(r => r.id === row.id);
                if (idx > -1) allContent[idx] = Object.assign({}, allContent[idx], row);
                render();
                paintCounts();
            } catch (err) {
                console.error('[CONTENT] update failed:', err);
                alert('Server error while updating.');
                cell.innerHTML = original;
            }
        };

        input.addEventListener('blur', function () { finish(true); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { done = true; cell.innerHTML = original; }
        });
    }

    const editModal = $('editModal');
    const editRef = $('editRef');
    const editTitle = $('editTitle');
    const editSubtitle = $('editSubtitle');
    const editStream = $('editStream');
    const editLabel = $('editLabel');
    const editPrice = $('editPrice');
    const editDiscount = $('editDiscount');
    const editStatus = $('editStatus');
    const editMaxTests = $('editMaxTests');
    const editMaxTestsHint = $('editMaxTestsHint');
    const editSave = $('editSave');
    const editSyllabusFile = $('editSyllabusFile');
    const editSyllabusLink = $('editSyllabusLink');
    const editSyllabusNone = $('editSyllabusNone');
    const editSyllabusRemove = $('editSyllabusRemove');
    const editSyllabusLabel = $('editSyllabusLabel');
    const editSyllabusPosition = $('editSyllabusPosition');
    let removeSyllabus = false;
    let editQuill = null;
    let editingRow = null;

    function syncEditPaidFields() {
        const paid = editLabel.value === 'Paid';
        syncPremiumButton('#ccEditToolbar', editLabel.value);
        editPrice.disabled = !paid;
        editDiscount.disabled = !paid;
        if (!paid) { editPrice.value = '0.00'; editDiscount.value = '0'; }
    }

    function openEdit(row) {
        if (!editModal) return;
        editingRow = row;
        editRef.textContent = row.code + ' - ' + (row.section || '') + ' - ID ' + row.id;
        editTitle.value = row.title || '';
        editSubtitle.value = row.subtitle || '';
        editStream.value = row.stream || '';
        editLabel.value = row.label === 'Paid' ? 'Paid' : 'Free';
        editPrice.value = Number(row.price || 0).toFixed(2);
        editDiscount.value = Number(row.discount || 0);
        editStatus.value = row.status === 'inactive' ? 'inactive' : 'active';
        if (editMaxTests) {
            editMaxTests.value = row.max_test_descriptions ? String(row.max_test_descriptions) : '';
            const used = Number(row.description_count || 0);
            editMaxTests.min = used > 0 ? String(used) : '1';
            if (editMaxTestsHint) {
                editMaxTestsHint.textContent = used + ' test description(s) already added. Blank = no limit; the limit cannot go below ' + Math.max(used, 1) + '.';
            }
        }
        syncEditPaidFields();

        removeSyllabus = false;
        if (editSyllabusFile) editSyllabusFile.value = '';
        if (editSyllabusLabel) editSyllabusLabel.value = row.syllabus_label || '';
        if (editSyllabusPosition) editSyllabusPosition.value = row.syllabus_position === 'above' ? 'above' : 'below';
        paintSyllabus(row.syllabus_url);

        if (!editQuill) {
            editQuill = makeEditor('#ccEditEditor', '#ccEditToolbar', 'Describe this content for students...');
        }
        if (editQuill) {
            editQuill.setContents([]);
            if (row.details) editQuill.clipboard.dangerouslyPasteHTML(0, row.details);
        }
        editModal.classList.add('is-open');
        editTitle.focus();
    }

    function closeEdit() {
        if (editModal) editModal.classList.remove('is-open');
        editingRow = null;
    }

    function paintSyllabus(url) {
        const has = !!url && !removeSyllabus;
        if (editSyllabusLink) {
            editSyllabusLink.hidden = !has;
            if (has) editSyllabusLink.href = url.indexOf('/static/') === 0 ? url : '/static/' + url;
        }
        if (editSyllabusNone) editSyllabusNone.hidden = has;
        if (editSyllabusRemove) editSyllabusRemove.hidden = !has;
    }

    if (editSyllabusRemove) {
        editSyllabusRemove.addEventListener('click', function () {
            removeSyllabus = true;
            if (editSyllabusFile) editSyllabusFile.value = '';
            paintSyllabus(editingRow ? editingRow.syllabus_url : null);
        });
    }
    if (editSyllabusFile) {
        editSyllabusFile.addEventListener('change', function () {
            if (this.files && this.files.length) removeSyllabus = false;
        });
    }

    function uploadSyllabusIfChosen(id) {
        if (!editSyllabusFile || !editSyllabusFile.files || !editSyllabusFile.files.length) {
            return Promise.resolve(true);
        }
        const fd = new FormData();
        fd.append('syllabus_file', editSyllabusFile.files[0]);
        return fetch('/update_content_syllabus/' + id, { method: 'POST', body: fd })
            .then(r => r.json())
            .then(function (data) {
                if (!data.success) { alert(data.message || 'Could not upload the syllabus.'); return false; }
                return true;
            })
            .catch(function (e) {
                console.error('[CONTENT] syllabus upload failed:', e);
                alert('Server error while uploading the syllabus.');
                return false;
            });
    }

    if (editLabel) editLabel.addEventListener('change', syncEditPaidFields);

    if (editSave) {
        editSave.addEventListener('click', async function () {
            if (!editingRow) return;
            const payload = {
                title: editTitle.value.trim(),
                subtitle: editSubtitle.value.trim(),
                stream: editStream.value.trim(),
                label: editLabel.value,
                status: editStatus.value,
                price: editLabel.value === 'Paid' ? editPrice.value : 0,
                discount: editLabel.value === 'Paid' ? editDiscount.value : 0,
                max_test_descriptions: editMaxTests ? editMaxTests.value.trim() : '',
                syllabus_position: editSyllabusPosition ? editSyllabusPosition.value : 'below',
                syllabus_label: editSyllabusLabel ? editSyllabusLabel.value.trim() : '',
                remove_syllabus: removeSyllabus,
                details: editQuill && editQuill.getLength() > 1 ? editQuill.root.innerHTML : ''
            };
            if (!payload.title) { alert('Title is required.'); return; }

            editSave.disabled = true;
            try {
                const fileOk = await uploadSyllabusIfChosen(editingRow.id);
                if (!fileOk) return;
                log('saving edit for id=' + editingRow.id);
                const res = await fetch('/update_content/' + editingRow.id, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                log('edit response', data);
                if (!data.success) { alert(data.message || 'Update failed.'); return; }
                const idx = allContent.findIndex(r => r.id === editingRow.id);
                if (idx > -1) allContent[idx] = Object.assign({}, allContent[idx], data.content || {});
                closeEdit();
                render();
                paintCounts();
            } catch (err) {
                console.error('[CONTENT] edit failed:', err);
                alert('Server error while saving.');
            } finally {
                editSave.disabled = false;
            }
        });
    }

    const closeEditBtn = $('closeEditModal');
    const cancelEditBtn = $('editCancel');
    if (closeEditBtn) closeEditBtn.addEventListener('click', closeEdit);
    if (cancelEditBtn) cancelEditBtn.addEventListener('click', closeEdit);
    if (editModal) editModal.addEventListener('click', function (e) { if (e.target === editModal) closeEdit(); });

    async function deleteContent(row) {
        if (!confirm('Delete "' + row.title + '" permanently? This cannot be undone.')) return;
        try {
            log('deleting id=' + row.id);
            const res = await fetch('/delete_content/' + row.id, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const data = await res.json();
            log('delete response', data);
            if (!data.success) { alert(data.message || 'Delete failed.'); return; }
            allContent = allContent.filter(r => r.id !== row.id);
            if (navCount) navCount.textContent = allContent.length;
            render();
            paintCounts();
        } catch (err) {
            console.error('[CONTENT] delete failed:', err);
            alert('Server error while deleting.');
        }
    }

    function closeModals() {
        imageModal.classList.remove('is-open');
        detailsModal.classList.remove('is-open');
        closeEdit();
    }

    const closeImg = $('closeImageModal');
    const closeDet = $('closeDetailsModal');
    if (closeImg) closeImg.addEventListener('click', closeModals);
    if (closeDet) closeDet.addEventListener('click', closeModals);
    [imageModal, detailsModal].forEach(function (m) {
        if (m) m.addEventListener('click', function (e) { if (e.target === m) closeModals(); });
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModals(); });

    const updateImageBtn = $('updateImageBtn');
    const deleteImageBtn = $('deleteImageBtn');

    if (updateImageBtn) {
        updateImageBtn.addEventListener('click', function () { newImageFile.click(); });
        newImageFile.addEventListener('change', function () {
            if (!this.files.length || !currentImageId) return;
            const fd = new FormData();
            fd.append('image_file', this.files[0]);
            fetch('/update_content_image/' + currentImageId, { method: 'POST', body: fd })
                .then(r => r.json())
                .then(function (data) {
                    log('image update response', data);
                    if (!data.success) { alert(data.message || 'Image update failed.'); return; }
                    const idx = allContent.findIndex(r => r.id === currentImageId);
                    if (idx > -1) allContent[idx].image_url = data.new_image_url.replace(/^\/static\//, '');
                    modalImage.src = data.new_image_url;
                    modalImage.style.display = 'block';
                    render();
                })
                .catch(function (e) { console.error('[CONTENT] image update failed:', e); alert('Server error.'); });
        });
    }

    if (deleteImageBtn) {
        deleteImageBtn.addEventListener('click', function () {
            if (!currentImageId || !confirm('Delete this image?')) return;
            fetch('/delete_content_image/' + currentImageId, { method: 'POST' })
                .then(r => r.json())
                .then(function (data) {
                    log('image delete response', data);
                    if (!data.success) { alert(data.message || 'Image delete failed.'); return; }
                    const idx = allContent.findIndex(r => r.id === currentImageId);
                    if (idx > -1) allContent[idx].image_url = '';
                    closeModals();
                    render();
                })
                .catch(function (e) { console.error('[CONTENT] image delete failed:', e); alert('Server error.'); });
        });
    }

    let searchTimer;
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(render, 180);
        });
    }
    if (labelFilter) labelFilter.addEventListener('change', function () {
        pickedLabel = labelFilter.value;
        render();
    });
    if (refreshBtn) refreshBtn.addEventListener('click', loadContent);
});
