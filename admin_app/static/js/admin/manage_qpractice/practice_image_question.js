document.addEventListener('DOMContentLoaded', function () {
    var modal = null;
    var fileInput = document.getElementById('piqFile');
    var stage = document.getElementById('piqStage');
    var img = document.getElementById('piqImage');
    var placeholder = document.getElementById('piqPlaceholder');
    var statusList = document.getElementById('piqStatus');
    var saveBtn = document.getElementById('piqSaveBtn');
    var msg = document.getElementById('piqMessage');
    var wrap = document.getElementById('piqCanvasWrap');
    if (!fileInput || !stage || !img || !saveBtn || !wrap) return;

    var toolGroup = document.getElementById('piqToolGroup');
    var toolHint = null;
    var undoBtn = document.getElementById('piqUndoBtn');
    var resetBtn = document.getElementById('piqResetBtn');
    var queueBadge = document.getElementById('piqQueueBadge');
    var skipBtn = document.getElementById('piqSkipBtn');
    var answerInput = document.getElementById('piqAnswer');
    var typeInput = document.getElementById('piqType');
    var el = function (id) { return document.getElementById(id); };

    fetch('/api/papers/codes').then(function (r) { return r.json(); }).then(function (codes) {
        var sel = el('piqPaperCode');
        sel.innerHTML = '<option value="">Select a Paper Code...</option>' + (codes || []).map(function (c) {
            return '<option>' + c + '</option>';
        }).join('');
    }).catch(function () {});
    el('piqPaperCode').addEventListener('change', function () {
        if (!this.value) return;
        fetch('/api/papers/subjects?paper_code=' + encodeURIComponent(this.value))
            .then(function (r) { return r.json(); })
            .then(function (subjects) {
                el('piqSubjectList').innerHTML = (subjects || []).map(function (s) { return '<option value="' + s + '">'; }).join('');
            }).catch(function () {});
    });

    var LETTERS = ['a', 'b', 'c', 'd'];
    var TOOL_HINTS = {
        option: 'Mark Options: drag over the row of option ',
        hide: 'Hide: drag over any part students must not see - it is whited out',
        crop: 'Crop: drag over the area to KEEP - everything outside is removed'
    };
    var regions = {};
    var activeLetter = 'a';
    var activeTool = 'option';
    var drawing = null;
    var queue = [];
    var queueIndex = -1;
    var originalImg = null;
    var opsList = [];
    var history = [];
    var workCanvas = null;
    var savedCount = 0;
    var editId = null;
    var editNumber = null;
    var previewOn = false;

    function say(text, kind) {
        if (window.adminToast) {
            var d = document.createElement('div');
            d.textContent = text;
            window.adminToast(d.innerHTML, kind === 'secondary' ? 'info' : (kind || 'danger'));
            return;
        }
        msg.className = 'alert alert-' + (kind || 'danger');
        msg.textContent = text;
        msg.classList.remove('is-hidden');
    }

    function ask(opts) {
        return window.adminConfirm ? window.adminConfirm(opts) : Promise.resolve(window.confirm(opts.title));
    }

    function copyRegions(src) { return JSON.parse(JSON.stringify(src || {})); }

    function checkpoint() {
        history.push({ ops: opsList.slice(), regions: copyRegions(regions) });
        if (history.length > 60) history.shift();
    }

    function setHint() {
        if (!toolHint) return;
        toolHint.textContent = activeTool === 'option'
            ? TOOL_HINTS.option + activeLetter.toUpperCase()
            : TOOL_HINTS[activeTool];
    }

    function paintStatus() {
        var answer = (answerInput.value || '').toUpperCase();
        statusList.innerHTML = LETTERS.map(function (l) {
            var done = !!regions[l];
            var correct = answer.indexOf(l.toUpperCase()) > -1;
            return '<li class="list-group-item d-flex justify-content-between py-2 ' + (done ? 'list-group-item-success' : '') + (correct ? ' fw-bold' : '') + '" data-letter="' + l + '" style="cursor:pointer" title="Click to make ' + l.toUpperCase() + ' the correct answer">' +
                '<span>Option ' + l.toUpperCase() + (correct ? ' <i class="fas fa-star text-warning"></i> correct' : '') + '</span>' +
                '<span>' + (done ? '<i class="fas fa-check"></i> marked' : 'not marked') + '</span></li>';
        }).join('');
    }

    function paintRegions() {
        stage.querySelectorAll('.piq-region').forEach(function (n) { n.remove(); });
        Object.keys(regions).forEach(function (l) {
            var r = regions[l];
            var box = document.createElement('div');
            box.className = 'piq-region';
            box.style.left = r.x + '%';
            box.style.top = r.y + '%';
            box.style.width = r.w + '%';
            box.style.height = r.h + '%';
            box.style.display = previewOn ? 'none' : '';
            box.innerHTML = '<span class="piq-region__tag">' + l.toUpperCase() + '</span>' +
                            '<button type="button" class="piq-region__del" data-letter="' + l + '" title="Remove option ' + l.toUpperCase() + ' area">&times;</button>';
            stage.appendChild(box);
        });
        paintStatus();
    }

    function updateQueueBadge() {
        if (editId) { queueBadge.hidden = false; queueBadge.textContent = 'Editing question #' + editNumber; skipBtn.hidden = true; return; }
        var remaining = queue.length - queueIndex - 1;
        if (queue.length > 1 || remaining > 0) {
            queueBadge.hidden = false;
            queueBadge.textContent = 'Image ' + (queueIndex + 1) + ' of ' + queue.length +
                (savedCount ? ' • ' + savedCount + ' saved' : '');
            skipBtn.hidden = remaining <= 0;
        } else {
            queueBadge.hidden = true;
            skipBtn.hidden = true;
        }
    }

    function renderCanvas() {
        if (!originalImg) return;
        var cv = document.createElement('canvas');
        cv.width = originalImg.naturalWidth;
        cv.height = originalImg.naturalHeight;
        cv.getContext('2d').drawImage(originalImg, 0, 0);

        opsList.forEach(function (op) {
            var r = op.r;
            if (op.type === 'rot') {
                var rcv = document.createElement('canvas');
                rcv.width = cv.height;
                rcv.height = cv.width;
                var rctx = rcv.getContext('2d');
                rctx.translate(rcv.width / 2, rcv.height / 2);
                rctx.rotate(Math.PI / 2);
                rctx.drawImage(cv, -cv.width / 2, -cv.height / 2);
                cv = rcv;
            } else if (op.type === 'crop') {
                var sx = r.x / 100 * cv.width;
                var sy = r.y / 100 * cv.height;
                var sw = Math.max(1, r.w / 100 * cv.width);
                var sh = Math.max(1, r.h / 100 * cv.height);
                var ncv = document.createElement('canvas');
                ncv.width = Math.max(1, Math.round(sw));
                ncv.height = Math.max(1, Math.round(sh));
                ncv.getContext('2d').drawImage(cv, sx, sy, sw, sh, 0, 0, ncv.width, ncv.height);
                cv = ncv;
            } else if (op.type === 'hide') {
                var ctx = cv.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(r.x / 100 * cv.width, r.y / 100 * cv.height,
                             r.w / 100 * cv.width, r.h / 100 * cv.height);
            }
        });

        workCanvas = cv;
        img.src = cv.toDataURL('image/png');
    }

    function round2(n) { return Math.round(n * 100) / 100; }

    function cropRegions(c) {
        var out = {};
        var lost = [];
        Object.keys(regions).forEach(function (l) {
            var r = regions[l];
            var x1 = Math.max(r.x, c.x), y1 = Math.max(r.y, c.y);
            var x2 = Math.min(r.x + r.w, c.x + c.w), y2 = Math.min(r.y + r.h, c.y + c.h);
            if (x2 - x1 <= 0.2 || y2 - y1 <= 0.2) { lost.push(l.toUpperCase()); return; }
            out[l] = {
                x: round2((x1 - c.x) / c.w * 100), y: round2((y1 - c.y) / c.h * 100),
                w: round2((x2 - x1) / c.w * 100), h: round2((y2 - y1) / c.h * 100)
            };
        });
        regions = out;
        return lost;
    }

    function rotateRegions() {
        var out = {};
        Object.keys(regions).forEach(function (l) {
            var r = regions[l];
            out[l] = { x: round2(100 - (r.y + r.h)), y: round2(r.x), w: round2(r.h), h: round2(r.w) };
        });
        regions = out;
    }

    function applyCrop(rect, label) {
        checkpoint();
        opsList.push({ type: 'crop', r: rect });
        var lost = cropRegions(rect);
        renderCanvas();
        paintRegions();
        say(label + (lost.length ? ' Option ' + lost.join(', ') + ' was outside the kept area - mark it again.' : ''),
            lost.length ? 'warning' : 'success');
    }

    function resetWork() {
        originalImg = null;
        workCanvas = null;
        opsList = [];
        history = [];
        regions = {};
        stage.hidden = true;
        placeholder.hidden = false;
        paintRegions();
    }

    function loadImageFile(file) {
        var reader = new FileReader();
        reader.onload = function () {
            var im = new Image();
            im.onload = function () {
                originalImg = im;
                opsList = [];
                history = [];
                regions = {};
                renderCanvas();
                placeholder.hidden = true;
                stage.hidden = false;
                pickLetter('a');
                paintRegions();
                updateQueueBadge();
            };
            im.onerror = function () { say('Could not read that image file. Use PNG, JPG or GIF.'); loadNext(); };
            im.src = reader.result;
        };
        reader.readAsDataURL(file);
    }

    function loadNext() {
        answerInput.value = '';
        if (previewOn) setPreview(false);
        queueIndex++;
        if (queueIndex >= queue.length) {
            resetWork();
            placeholder.textContent = savedCount
                ? 'All ' + savedCount + ' image question(s) saved. Upload more, or close this window.'
                : 'Click to upload, or drag & drop question image(s) here';
            fileInput.value = '';
            updateQueueBadge();
            return;
        }
        loadImageFile(queue[queueIndex]);
    }

    function enqueueFiles(fileList) {
        var files = Array.prototype.filter.call(fileList || [], function (f) {
            return f && (!f.type || f.type.indexOf('image/') === 0);
        });
        if (!files.length) {
            return say('Only image files are allowed (PNG, JPG, JPEG, GIF).');
        }
        if (editId) { editId = null; editNumber = null; }
        var wasIdle = !originalImg;
        files.forEach(function (f) { queue.push(f); });
        if (wasIdle) {
            loadNext();
        } else {
            updateQueueBadge();
            say(files.length + ' image(s) added to the queue.', 'success');
        }
    }

    fileInput.addEventListener('change', function () { enqueueFiles(this.files); });

    window.ppiqOpenForEdit = function (q) {
        editId = q.id;
        editNumber = q.question_id;
        queue = [];
        queueIndex = -1;
        savedCount = 0;
        if (previewOn) setPreview(false);
        var im = new Image();
        im.onload = function () {
            originalImg = im;
            opsList = [];
            history = [];
            try {
                regions = typeof q.option_regions === 'string'
                    ? (JSON.parse(q.option_regions) || {})
                    : copyRegions(q.option_regions);
            } catch (err) { regions = {}; }
            renderCanvas();
            placeholder.hidden = true;
            stage.hidden = false;
            paintRegions();
            updateQueueBadge();
            say('Editing question #' + q.question_id + '. Adjust and Save to update it.', 'info');
        };
        im.onerror = function () { say('Could not load the stored question image.'); };
        im.src = q.question_image.charAt(0) === '/' ? q.question_image : '/' + q.question_image;

        typeInput.value = (q.question_type || 'MCQ').toUpperCase() === 'MSQ' ? 'MSQ' : 'MCQ';
        el('piqPaperCode').value = q.paper_code || '';
        el('piqSubject').value = q.subject || '';
        el('piqTopic').value = q.topic || '';
        el('piqYear').value = q.year || '';
        el('piqPaperSet').value = q.paper_set || '';
        answerInput.value = q.correct_option || '';
        paintStatus();
    };

    wrap.addEventListener('click', function () {
        if (!stage.hidden) return;
        fileInput.click();
    });
    ['dragenter', 'dragover'].forEach(function (type) {
        wrap.addEventListener(type, function (e) {
            e.preventDefault(); e.stopPropagation();
            wrap.classList.add('is-dragover');
        });
    });
    ['dragleave', 'drop'].forEach(function (type) {
        wrap.addEventListener(type, function (e) {
            e.preventDefault(); e.stopPropagation();
            wrap.classList.remove('is-dragover');
        });
    });
    wrap.addEventListener('drop', function (e) {
        enqueueFiles(e.dataTransfer && e.dataTransfer.files);
    });
    document.addEventListener('paste', function (e) {
        if (!document.querySelector('#ppView-image.is-active')) return;
        var items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        for (var i = 0; i < items.length; i++) {
            if (items[i].type && items[i].type.indexOf('image/') === 0) {
                enqueueFiles([items[i].getAsFile()]);
                e.preventDefault();
                return;
            }
        }
    });

    skipBtn.addEventListener('click', function () { loadNext(); });

    function pickTool(tool) {
        activeTool = tool;
        toolGroup.querySelectorAll('button').forEach(function (b) { b.classList.toggle('active', b.dataset.tool === tool); });
        stage.dataset.tool = tool;
        setHint();
    }

    function pickLetter(letter) {
        activeLetter = letter;
        document.querySelectorAll('#piqLetterGroup [data-letter]').forEach(function (b) {
            b.classList.toggle('active', b.dataset.letter === letter);
        });
        setHint();
    }

    toolGroup.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-tool]');
        if (btn) pickTool(btn.dataset.tool);
    });

    function undoEdit() {
        if (!history.length) return say('Nothing to undo.', 'secondary');
        var snap = history.pop();
        opsList = snap.ops;
        regions = snap.regions;
        renderCanvas();
        paintRegions();
        say('Undone.', 'info');
    }
    undoBtn.addEventListener('click', undoEdit);

    var autoTrimBtn = document.getElementById('piqAutoTrimBtn');
    var rotateBtn = document.getElementById('piqRotateBtn');
    var previewBtn = null;

    function autoTrim() {
        if (!workCanvas) return say('Upload a question image first.', 'warning');
        var w = workCanvas.width, h = workCanvas.height;
        var data;
        try {
            data = workCanvas.getContext('2d').getImageData(0, 0, w, h).data;
        } catch (err) {
            return say('Could not analyse the image for trimming.');
        }
        var THRESHOLD = 242;
        var minX = w, minY = h, maxX = -1, maxY = -1;
        var stepX = Math.max(1, Math.floor(w / 1200));
        var stepY = Math.max(1, Math.floor(h / 1200));
        for (var y = 0; y < h; y += stepY) {
            for (var x = 0; x < w; x += stepX) {
                var i = (y * w + x) * 4;
                if (data[i + 3] > 40 &&
                    (data[i] < THRESHOLD || data[i + 1] < THRESHOLD || data[i + 2] < THRESHOLD)) {
                    if (x < minX) minX = x;
                    if (x > maxX) maxX = x;
                    if (y < minY) minY = y;
                    if (y > maxY) maxY = y;
                }
            }
        }
        if (maxX < 0) return say('The image looks blank - nothing to trim.', 'warning');
        var padX = w * 0.01, padY = h * 0.01;
        minX = Math.max(0, minX - padX); minY = Math.max(0, minY - padY);
        maxX = Math.min(w, maxX + padX); maxY = Math.min(h, maxY + padY);
        var rect = {
            x: round2(minX / w * 100), y: round2(minY / h * 100),
            w: round2((maxX - minX) / w * 100), h: round2((maxY - minY) / h * 100)
        };
        if (rect.w > 98.5 && rect.h > 98.5) return say('No blank margins found to trim.', 'secondary');
        applyCrop(rect, 'Blank margins trimmed.');
    }
    if (autoTrimBtn) autoTrimBtn.addEventListener('click', autoTrim);

    if (rotateBtn) rotateBtn.addEventListener('click', function () {
        if (!originalImg) return say('Upload a question image first.', 'warning');
        checkpoint();
        opsList.push({ type: 'rot' });
        rotateRegions();
        renderCanvas();
        paintRegions();
    });

    function setPreview(on) {
        previewOn = on;
        stage.classList.toggle('is-preview', on);
        if (previewBtn) previewBtn.classList.toggle('active', on);
        stage.querySelectorAll('.piq-preview-dot').forEach(function (n) { n.remove(); });
        if (on) {
            Object.keys(regions).forEach(function (l) {
                var r = regions[l];
                var dot = document.createElement('span');
                dot.className = 'piq-preview-dot';
                dot.style.top = (r.y + r.h / 2) + '%';
                dot.title = 'Option ' + l.toUpperCase();
                stage.appendChild(dot);
            });
        }
        stage.querySelectorAll('.piq-region').forEach(function (n) { n.style.display = on ? 'none' : ''; });
    }

    resetBtn.addEventListener('click', function () {
        if (!originalImg) return;
        checkpoint();
        opsList = [];
        regions = {};
        renderCanvas();
        paintRegions();
        say('Image restored to the original. Undo brings your edits back.', 'success');
    });

    document.getElementById('piqLetterGroup').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-letter]');
        if (!btn) return;
        pickLetter(btn.dataset.letter);
        pickTool('option');
    });

    statusList.addEventListener('click', function (e) {
        var li = e.target.closest('li[data-letter]');
        if (!li) return;
        var letter = li.dataset.letter;
        if (!regions[letter]) return say('Mark option ' + letter.toUpperCase() + ' on the image first.', 'warning');
        var up = letter.toUpperCase();
        if (typeInput.value === 'MSQ') {
            var cur = (answerInput.value || '').toUpperCase().replace(/[^A-D]/g, '');
            answerInput.value = cur.indexOf(up) > -1
                ? cur.replace(up, '')
                : cur.split('').concat(up).sort().join('');
        } else {
            answerInput.value = up;
        }
        paintStatus();
    });
    answerInput.addEventListener('input', paintStatus);
    typeInput.addEventListener('change', function () {
        var cur = (answerInput.value || '').toUpperCase().replace(/[^A-D]/g, '');
        if (typeInput.value === 'MCQ' && cur.length > 1) answerInput.value = cur[0];
        paintStatus();
    });

    document.addEventListener('keydown', function (e) {
        if (!document.querySelector('#ppView-image.is-active')) return;
        if (document.body.classList.contains('acf-open')) return;
        var t = e.target;
        if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
        var key = e.key.toLowerCase();
        if ((e.ctrlKey || e.metaKey) && key === 'z') {
            e.preventDefault();
            undoEdit();
        } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            saveBtn.click();
        } else if (!e.ctrlKey && !e.metaKey && LETTERS.indexOf(key) > -1) {
            pickLetter(key);
            pickTool('option');
        } else if (['1', '2', '3'].indexOf(key) > -1) {
            pickTool(['option', 'hide', 'crop'][+key - 1]);
        } else if (key === 't') {
            autoTrim();
        }
    });

    stage.addEventListener('click', function (e) {
        var del = e.target.closest('.piq-region__del');
        if (!del) return;
        e.stopPropagation();
        checkpoint();
        delete regions[del.dataset.letter];
        paintRegions();
    });

    document.getElementById('piqClearRegions').addEventListener('click', function () {
        if (!Object.keys(regions).length) return;
        checkpoint();
        regions = {};
        paintRegions();
        say('All option areas cleared. Undo brings them back.', 'info');
    });

    function pct(evt) {
        var rect = img.getBoundingClientRect();
        return {
            x: Math.min(Math.max((evt.clientX - rect.left) / rect.width * 100, 0), 100),
            y: Math.min(Math.max((evt.clientY - rect.top) / rect.height * 100, 0), 100)
        };
    }

    stage.addEventListener('pointerdown', function (e) {
        if (e.button !== undefined && e.button !== 0) return;
        if (e.target.closest('.piq-region__del') || stage.hidden || !originalImg) return;
        if (previewOn) setPreview(false);
        var p = pct(e);
        drawing = { startX: p.x, startY: p.y, el: document.createElement('div'), id: e.pointerId };
        drawing.el.className = 'piq-region piq-region--draft piq-region--' + activeTool;
        stage.appendChild(drawing.el);
        try { stage.setPointerCapture(e.pointerId); } catch (err) {}
        e.preventDefault();
    });

    stage.addEventListener('pointermove', function (e) {
        if (!drawing || e.pointerId !== drawing.id) return;
        var p = pct(e);
        var x = Math.min(drawing.startX, p.x);
        var y = Math.min(drawing.startY, p.y);
        var w = Math.abs(p.x - drawing.startX);
        var h = Math.abs(p.y - drawing.startY);
        Object.assign(drawing.el.style, { left: x + '%', top: y + '%', width: w + '%', height: h + '%' });
        drawing.box = { x: x, y: y, w: w, h: h };
    });

    function finishDrawing(e) {
        if (!drawing || (e && e.pointerId !== drawing.id)) return;
        var box = drawing.box;
        drawing.el.remove();
        try { stage.releasePointerCapture(drawing.id); } catch (err) {}
        drawing = null;
        if (!box || box.w < 1 || box.h < 1) return;
        var rounded = { x: round2(box.x), y: round2(box.y), w: round2(box.w), h: round2(box.h) };

        if (activeTool === 'hide') {
            checkpoint();
            opsList.push({ type: 'hide', r: rounded });
            renderCanvas();
            return;
        }
        if (activeTool === 'crop') {
            applyCrop(rounded, 'Cropped.');
            return;
        }

        checkpoint();
        var replaced = !!regions[activeLetter];
        regions[activeLetter] = rounded;
        paintRegions();
        if (replaced) say('Option ' + activeLetter.toUpperCase() + ' area replaced.', 'info');
        var next = LETTERS.filter(function (l) { return !regions[l]; })[0];
        if (next) pickLetter(next);
    }
    stage.addEventListener('pointerup', finishDrawing);
    stage.addEventListener('pointercancel', finishDrawing);

    function uploadCanvas() {
        return new Promise(function (resolve, reject) {
            workCanvas.toBlob(function (blob) {
                if (!blob) return reject(new Error('Could not export the edited image.'));
                var fd = new FormData();
                fd.append('image', blob, 'practice_question.png');
                fetch('/api/question-image/upload', { method: 'POST', body: fd })
                    .then(function (r) {
                        return r.json()
                            .catch(function () { throw new Error('Server error (' + r.status + '). Please try again.'); })
                            .then(function (d) {
                                if (!r.ok || !d.url) throw new Error(d.message || 'Upload failed');
                                resolve(d.url);
                            });
                    })
                    .catch(reject);
            }, 'image/png');
        });
    }

    function validAnswer() {
        var answer = (answerInput.value || '').trim().toUpperCase().replace(/[\s,]/g, '');
        if (!answer) return say('Set the correct answer - type it or click an option row on the left.'), null;
        if (!/^[A-D]+$/.test(answer)) return say('The answer can only use the letters A, B, C and D.'), null;
        if (typeInput.value === 'MCQ' && answer.length !== 1) return say('An MCQ has exactly one correct letter. Switch the type to MSQ for more.'), null;
        if (new Set(answer.split('')).size !== answer.length) return say('Each letter can appear only once in the answer.'), null;
        for (var i = 0; i < answer.length; i++) {
            if (!regions[answer[i].toLowerCase()]) {
                return say('Option ' + answer[i] + ' is set as correct but its area is not marked.'), null;
            }
        }
        return answer.split('').sort().join('');
    }

    function doSave(answer) {
        saveBtn.disabled = true;
        uploadCanvas().then(function (url) {
            var payload = {
                paper_code: el('piqPaperCode').value,
                subject: el('piqSubject').value.trim(),
                topic: el('piqTopic').value.trim(),
                year: el('piqYear').value,
                paper_set: el('piqPaperSet').value.trim(),
                question_type: typeInput.value,
                correct_option: answer,
                question_image: url,
                option_regions: regions
            };
            var endpoint = editId ? '/api/practice-questions/update-image/' + editId : '/api/practice-questions/add-image';
            return fetch(endpoint, { method: editId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); });
        }).then(function (res) {
            saveBtn.disabled = false;
            say(res.d.message || (res.ok ? 'Saved.' : 'Failed.'), res.ok ? 'success' : 'danger');
            if (!res.ok) return;
            if (editId) {
                editId = null;
                editNumber = null;
                queueBadge.hidden = true;
                resetWork();
                placeholder.textContent = 'Question updated. Upload new images, or switch view.';
                answerInput.value = '';
                if (typeof window.ppShowView === 'function') window.ppShowView('search');
            } else {
                savedCount++;
                loadNext();
            }
        }).catch(function (err) {
            saveBtn.disabled = false;
            say(err.message || 'Could not save the question.');
        });
    }

    saveBtn.addEventListener('click', function () {
        if (!workCanvas) return say('Upload a question image first.');
        if (!el('piqPaperCode').value) return say('Pick the Paper Code.');
        if (!el('piqSubject').value.trim()) return say('Enter the Subject.');
        if (!Object.keys(regions).length) return say('Mark at least one option area on the image.');
        var answer = validAnswer();
        if (!answer) return;
        if (!editId) return doSave(answer);
        ask({
            tone: 'primary',
            title: 'Save changes to question #' + editNumber + '?',
            message: 'The stored image, option areas and answer are replaced with what is on screen now.',
            items: [{ label: 'Answer', value: answer }, { label: 'Option areas', value: Object.keys(regions).map(function (l) { return l.toUpperCase(); }).sort().join(', ') }],
            confirmText: 'Save changes'
        }).then(function (ok) { if (ok) doSave(answer); });
    });

    pickTool('option');
    pickLetter('a');
    paintStatus();
});
