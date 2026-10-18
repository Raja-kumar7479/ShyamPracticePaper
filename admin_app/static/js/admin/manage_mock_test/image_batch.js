document.addEventListener('DOMContentLoaded', function () {
    var LETTERS = ['a', 'b', 'c', 'd'];
    var items = [];
    var current = -1;
    var activeLetter = 'a';
    var drawing = null;

    function el(id) { return document.getElementById(id); }
    function esc(v) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }
    function msg(id, text, kind) {
        var box = el(id);
        box.className = 'alert mt-3 alert-' + (kind || 'danger');
        box.classList.remove('d-none');
        box.innerHTML = text;
    }

    var params = new URLSearchParams(window.location.search);
    var want = { test: params.get('test') || '', desc: params.get('desc') || '', sid: params.get('sid') || '', sname: params.get('sname') || '' };
    var NOT_IMAGE = ['communication_test', 'coding_test'];

    function sectionTarget() {
        var v = el('ibSection').value;
        if (v === '__new__') {
            return { id: el('ibSectionId').value.trim(), name: el('ibSectionName').value.trim(), isNew: true };
        }
        var opt = el('ibSection').options[el('ibSection').selectedIndex];
        return v ? { id: v, name: opt.dataset.name, isNew: false } : { id: '', name: '' };
    }

    function loadSections(descId) {
        var sel = el('ibSection');
        el('ibNewSection').classList.add('d-none');
        if (!descId) { sel.innerHTML = '<option value="">Select a description first</option>'; return; }
        sel.innerHTML = '<option value="">Loading…</option>';
        fetch('/api/test-sections/' + encodeURIComponent(descId), { headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                var rows = (d && d.sections) || [];
                sel.innerHTML = '<option value="">- pick a section -</option>' + rows.map(function (x) {
                    return '<option value="' + esc(x.section_id) + '" data-name="' + esc(x.section_name) + '">' +
                        esc(x.section_name + ' (' + x.section_id + ') - ' + x.questions + ' question' + (x.questions === 1 ? '' : 's')) + '</option>';
                }).join('') + '<option value="__new__">+ Create a new section</option>';
                if (want.sid) {
                    var known = rows.some(function (x) { return String(x.section_id) === want.sid; });
                    if (known) {
                        sel.value = want.sid;
                    } else {
                        sel.value = '__new__';
                        el('ibNewSection').classList.remove('d-none');
                        el('ibSectionId').value = want.sid;
                        el('ibSectionName').value = want.sname;
                    }
                    want.sid = '';
                }
            })
            .catch(function () { sel.innerHTML = '<option value="">Could not load sections</option>'; });
    }

    el('ibSection').addEventListener('change', function () {
        el('ibNewSection').classList.toggle('d-none', this.value !== '__new__');
    });

    fetch('/api/content-for-tests').then(function (r) { return r.json(); }).then(function (rows) {
        var sel = el('ibTest');
        var groups = {};
        (rows || []).filter(function (r) { return NOT_IMAGE.indexOf(r.section) === -1; }).forEach(function (r) {
            var g = (r.course_name || 'Other') + ' › ' + (r.code || '-') + (r.course_subgroup ? ' · ' + r.course_subgroup : '');
            (groups[g] = groups[g] || []).push(r);
        });
        sel.innerHTML = '<option value="">- pick a mock test -</option>' + Object.keys(groups).sort().map(function (g) {
            return '<optgroup label="' + esc(g) + '">' + groups[g].map(function (r) {
                return '<option value="' + esc(r.test_id) + '">' + esc(r.title) + '</option>';
            }).join('') + '</optgroup>';
        }).join('');
        if (want.test) {
            sel.value = want.test;
            want.test = '';
            sel.dispatchEvent(new Event('change'));
        }
    }).catch(function () { el('ibTest').innerHTML = '<option value="">Could not load tests</option>'; });

    el('ibTest').addEventListener('change', function () {
        var sel = el('ibDesc');
        loadSections('');
        sel.innerHTML = '<option value="">Loading…</option>';
        if (!this.value) { sel.innerHTML = '<option value="">Select a test first</option>'; return; }
        fetch('/api/test-descriptions/' + encodeURIComponent(this.value))
            .then(function (r) { return r.json(); })
            .then(function (rows) {
                var usable = (rows || []).filter(function (d) { return Number(d.id) < 1000000; });
                sel.innerHTML = (usable.length ? '<option value="">- pick a description -</option>' : '<option value="">No competitive test description here</option>') +
                    usable.map(function (d) {
                        return '<option value="' + d.id + '" data-key="' + esc(d.test_key) + '" data-testid="' + esc(d.test_id) + '">' +
                            esc(d.subject_title + ' (' + d.total_questions + ' Q)') + '</option>';
                    }).join('');
                if (want.desc) {
                    sel.value = want.desc;
                    want.desc = '';
                    loadSections(sel.value);
                }
            });
    });

    el('ibDesc').addEventListener('change', function () { loadSections(this.value); });

    el('ibTemplateBtn').addEventListener('click', function (e) {
        e.preventDefault();
        var rows = [
            ['image_filename', 'question_type', 'correct_option', 'correct_marks', 'negative_marks', 'question_level'],
            ['q1.png', 'MCQ', 'b', '1', '1/3', 'Medium'],
            ['q2.png', 'MCQ', 'a', '2', '0.5', 'Easy'],
            ['q3.png', 'MSQ', 'ac', '2', '0', 'Tough']
        ];
        var ws = XLSX.utils.aoa_to_sheet(rows);
        var wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Questions');
        XLSX.writeFile(wb, 'image_question_batch_template.xlsx');
    });

    function parseSheet(file) {
        return file.arrayBuffer().then(function (buf) {
            var wb = XLSX.read(buf, { type: 'array' });
            var ws = wb.Sheets[wb.SheetNames[0]];
            return XLSX.utils.sheet_to_json(ws, { defval: '' });
        });
    }

    el('ibLoadBtn').addEventListener('click', function () {
        var sheet = el('ibSheet').files[0];
        var files = el('ibImages').files;
        if (!el('ibDesc').value) return msg('ibLoadMsg', 'Pick the test and description first (Step 1).');
        var target = sectionTarget();
        if (!target.id || !target.name) return msg('ibLoadMsg', 'Pick a section in Step 1, or choose "Create a new section" and fill its ID and name.');
        if (!/^[A-Za-z0-9_-]{1,50}$/.test(target.id)) return msg('ibLoadMsg', 'Section ID: 1-50 letters, numbers, - or _ (no spaces), for example SEC1.');
        if (!sheet) return msg('ibLoadMsg', 'Choose the Excel/CSV sheet.');
        if (!files.length) return msg('ibLoadMsg', 'Select the question images (you can select all at once).');

        var byName = {};
        Array.prototype.forEach.call(files, function (f) { byName[f.name.toLowerCase()] = f; });

        parseSheet(sheet).then(function (rows) {
            if (!rows.length) return msg('ibLoadMsg', 'The sheet has no data rows.');
            items = [];
            var missing = [];
            rows.forEach(function (row, i) {
                var fname = String(row.image_filename || row.image || '').trim();
                if (!fname) return;
                var file = byName[fname.toLowerCase()];
                if (!file) { missing.push(fname); return; }
                items.push({
                    file: file,
                    fileName: fname,
                    rowNumber: i + 2,
                    qtype: String(row.question_type || 'MCQ').trim().toUpperCase() === 'MSQ' ? 'MSQ' : 'MCQ',
                    answer: String(row.correct_option || '').trim().toLowerCase().replace(/[^a-d]/g, ''),
                    marks: String(row.correct_marks || '1'),
                    negative: String(row.negative_marks || ''),
                    level: String(row.question_level || 'Medium'),
                    regions: {},
                    dataUrl: null,
                    saved: false
                });
            });
            if (!items.length) {
                return msg('ibLoadMsg', 'No usable rows. ' + (missing.length ? 'Images not found for: ' + missing.join(', ') : 'Check the image_filename column.'));
            }
            var text = '<strong><i class="fas fa-check-circle me-1"></i>All ' + items.length + ' images uploaded &amp; matched successfully.</strong>';
            if (missing.length) text += '<br>Rows skipped (image file not selected): ' + esc(missing.join(', '));
            msg('ibLoadMsg', text, missing.length ? 'warning' : 'success');
            el('ibMarkerCard').classList.remove('d-none');
            buildThumbs();
            show(0);
            el('ibMarkerCard').scrollIntoView({ behavior: 'smooth' });
        }).catch(function () { msg('ibLoadMsg', 'Could not read the sheet - is it a valid .xlsx or .csv file?'); });
    });

    function buildThumbs() {
        var box = el('ibThumbs');
        box.innerHTML = '';
        items.forEach(function (it, i) {
            var t = document.createElement('div');
            t.className = 'ib-thumb';
            t.textContent = i + 1;
            t.title = it.fileName;
            t.addEventListener('click', function () { persist(); show(i); });
            box.appendChild(t);
        });
    }

    function paintThumbs() {
        var nodes = el('ibThumbs').children;
        items.forEach(function (it, i) {
            nodes[i].className = 'ib-thumb' + (isComplete(it) ? ' done' : '') + (i === current ? ' current' : '');
        });
    }

    function isComplete(it) {
        if (!it.answer || !Object.keys(it.regions).length) return false;
        if (it.qtype === 'MCQ' && it.answer.length !== 1) return false;
        if (!(parseFloat(it.marks) > 0)) return false;
        for (var i = 0; i < it.answer.length; i++) {
            if (!it.regions[it.answer[i]]) return false;
        }
        return true;
    }

    function persist() {
        if (current < 0 || !items[current]) return;
        var it = items[current];
        it.qtype = el('ibQType').value;
        it.level = el('ibQLevel').value;
        it.marks = el('ibQMarks').value;
        it.negative = el('ibQNegative').value;
        it.answer = el('ibQAnswer').value.trim().toLowerCase().replace(/[^a-d]/g, '');
    }

    function show(i) {
        current = i;
        var it = items[i];
        el('ibProgress').textContent = 'Question ' + (i + 1) + ' of ' + items.length;
        el('ibFileName').textContent = it.fileName;
        el('ibQType').value = it.qtype;
        el('ibQLevel').value = /^(Easy|Medium|Tough)$/i.test(it.level) ? it.level : 'Medium';
        el('ibQMarks').value = it.marks;
        el('ibQNegative').value = it.negative;
        el('ibQAnswer').value = it.answer;
        el('ibPrevBtn').disabled = i === 0;
        el('ibNextBtn').disabled = i === items.length - 1;
        setLetter('a');

        if (it.dataUrl) {
            el('ibImage').src = it.dataUrl;
            paintRegions();
        } else {
            var reader = new FileReader();
            reader.onload = function () {
                it.dataUrl = reader.result;
                el('ibImage').src = it.dataUrl;
                paintRegions();
            };
            reader.readAsDataURL(it.file);
        }
        el('ibCanvas').scrollTop = 0;
        paintThumbs();
    }

    function setLetter(l) {
        activeLetter = l;
        document.querySelectorAll('#ibLetterGroup button').forEach(function (b) {
            b.classList.toggle('active', b.dataset.letter === l);
        });
    }

    el('ibLetterGroup').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-letter]');
        if (btn) setLetter(btn.dataset.letter);
    });

    function paintRegions() {
        var stage = el('ibStage');
        stage.querySelectorAll('.ib-region').forEach(function (n) { n.remove(); });
        var it = items[current];
        if (!it) return;
        Object.keys(it.regions).forEach(function (l) {
            var r = it.regions[l];
            var box = document.createElement('div');
            box.className = 'ib-region';
            box.style.left = r.x + '%';
            box.style.top = r.y + '%';
            box.style.width = r.w + '%';
            box.style.height = r.h + '%';
            box.innerHTML = '<span class="ib-region__tag">' + l.toUpperCase() + '</span>' +
                '<button type="button" class="ib-region__del" data-letter="' + l + '">&times;</button>';
            stage.appendChild(box);
        });
        paintStatus();
        paintThumbs();
    }

    function paintStatus() {
        var it = items[current] || { regions: {} };
        el('ibStatus').innerHTML = LETTERS.map(function (l) {
            var done = !!it.regions[l];
            return '<li class="list-group-item d-flex justify-content-between py-2 ' + (done ? 'list-group-item-success' : '') + '">' +
                '<span>Option ' + l.toUpperCase() + '</span><span>' + (done ? '<i class="fas fa-check"></i> marked' : 'not marked') + '</span></li>';
        }).join('');
    }

    el('ibStage').addEventListener('click', function (e) {
        var del = e.target.closest('.ib-region__del');
        if (!del) return;
        e.stopPropagation();
        delete items[current].regions[del.dataset.letter];
        paintRegions();
    });

    el('ibClearBtn').addEventListener('click', function () {
        if (items[current]) { items[current].regions = {}; paintRegions(); }
    });

    function pct(evt) {
        var rect = el('ibImage').getBoundingClientRect();
        return {
            x: Math.min(Math.max((evt.clientX - rect.left) / rect.width * 100, 0), 100),
            y: Math.min(Math.max((evt.clientY - rect.top) / rect.height * 100, 0), 100)
        };
    }

    el('ibStage').addEventListener('pointerdown', function (e) {
        if (e.button !== undefined && e.button !== 0) return;
        if (e.target.closest('.ib-region__del') || current < 0) return;
        var p = pct(e);
        drawing = { sx: p.x, sy: p.y, el: document.createElement('div'), id: e.pointerId };
        drawing.el.className = 'ib-region ib-region--draft';
        el('ibStage').appendChild(drawing.el);
        try { el('ibStage').setPointerCapture(e.pointerId); } catch (err) {}
        e.preventDefault();
    });
    el('ibStage').addEventListener('pointermove', function (e) {
        if (!drawing || e.pointerId !== drawing.id) return;
        var p = pct(e);
        var x = Math.min(drawing.sx, p.x), y = Math.min(drawing.sy, p.y);
        var w = Math.abs(p.x - drawing.sx), h = Math.abs(p.y - drawing.sy);
        Object.assign(drawing.el.style, { left: x + '%', top: y + '%', width: w + '%', height: h + '%' });
        drawing.box = { x: x, y: y, w: w, h: h };
    });
    function endDraw(e) {
        if (!drawing || (e && e.pointerId !== drawing.id)) return;
        var box = drawing.box;
        drawing.el.remove();
        try { el('ibStage').releasePointerCapture(drawing.id); } catch (err) {}
        drawing = null;
        if (!box || box.w < 1 || box.h < 1 || current < 0) return;
        items[current].regions[activeLetter] = {
            x: +box.x.toFixed(2), y: +box.y.toFixed(2), w: +box.w.toFixed(2), h: +box.h.toFixed(2)
        };
        paintRegions();
        var next = LETTERS.filter(function (l) { return !items[current].regions[l]; })[0];
        if (next) setLetter(next);
    }
    el('ibStage').addEventListener('pointerup', endDraw);
    el('ibStage').addEventListener('pointercancel', endDraw);

    el('ibPrevBtn').addEventListener('click', function () { persist(); if (current > 0) show(current - 1); });
    el('ibNextBtn').addEventListener('click', function () { persist(); if (current < items.length - 1) show(current + 1); });

    function uploadImage(it) {
        var fd = new FormData();
        fd.append('image', it.file, it.fileName);
        return fetch('/api/question-image/upload', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.url) throw new Error(d.message || 'image upload failed');
                return d.url;
            });
    }

    el('ibSaveAllBtn').addEventListener('click', function () {
        persist();
        var descSel = el('ibDesc');
        var opt = descSel.options[descSel.selectedIndex];
        if (!descSel.value) return msg('ibSaveMsg', 'Pick the test description in Step 1.');
        if (!sectionTarget().id || !sectionTarget().name) return msg('ibSaveMsg', 'Pick the section in Step 1.');
        var ready = items.filter(function (it) { return !it.saved && isComplete(it); });
        var incomplete = items.filter(function (it) { return !it.saved && !isComplete(it); });
        if (!ready.length) {
            return msg('ibSaveMsg', 'No completed questions to save yet - every question needs marks above 0, a valid answer (one letter for MCQ) and a marked area for each correct option.', 'warning');
        }

        var btn = el('ibSaveAllBtn');
        btn.disabled = true;
        var log = el('ibSaveLog');
        log.innerHTML = '';
        msg('ibSaveMsg', 'Saving ' + ready.length + ' question(s)…', 'info');

        var okCount = 0, failCount = 0;
        var chain = Promise.resolve();
        ready.forEach(function (it) {
            chain = chain.then(function () {
                return uploadImage(it).then(function (url) {
                    return fetch('/api/test-questions/add-image', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            test_id: opt.dataset.testid,
                            test_key: opt.dataset.key,
                            test_description_id: descSel.value,
                            section_id: sectionTarget().id,
                            section_name: sectionTarget().name,
                            question_image: url,
                            option_regions: it.regions,
                            question_type: it.qtype,
                            question_level: it.level,
                            correct_marks: it.marks,
                            negative_marks: it.negative,
                            correct_option: it.answer.toUpperCase()
                        })
                    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); });
                }).then(function (res) {
                    if (res.ok) { it.saved = true; okCount++; }
                    else failCount++;
                    log.innerHTML += '<div class="' + (res.ok ? 'text-success' : 'text-danger') + '">' +
                        (res.ok ? '<i class="fas fa-check me-1"></i>' : '<i class="fas fa-xmark me-1"></i>') +
                        esc(it.fileName) + ' - ' + esc(res.d.message || (res.ok ? 'saved' : 'failed')) + '</div>';
                    paintThumbs();
                }).catch(function (err) {
                    failCount++;
                    log.innerHTML += '<div class="text-danger"><i class="fas fa-xmark me-1"></i>' + esc(it.fileName) + ' - ' + esc(err.message) + '</div>';
                });
            });
        });
        chain.then(function () {
            btn.disabled = false;
            var summary = '<strong>' + okCount + ' saved</strong>' +
                (failCount ? ', ' + failCount + ' failed (see log below)' : '') +
                (incomplete.length ? ', ' + incomplete.length + ' still incomplete (not saved)' : '') + '.';
            msg('ibSaveMsg', summary, failCount ? 'warning' : 'success');
            if (okCount) {
                var t = sectionTarget();
                want.sid = t.id;
                want.sname = t.name;
                loadSections(el('ibDesc').value);
            }
        });
    });
});
