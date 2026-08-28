(function () {
    var page = document.getElementById('pageData');
    if (!page) return;
    var testKey = page.dataset.testKey;

    function currentQuestion() {
        var tm = window.testManager;
        if (tm && tm.questions && tm.currentQuestionIndex > -1) {
            return tm.questions[tm.currentQuestionIndex] || null;
        }
        return null;
    }

    var flagBtn = document.getElementById('flag-question-btn');
    var flagged = {};

    function paintFlag() {
        if (!flagBtn) return;
        var q = currentQuestion();
        var on = q ? !!flagged[q.id] : false;
        flagBtn.classList.toggle('is-flagged', on);
        var label = flagBtn.querySelector('span');
        if (label) label.textContent = on ? 'Flagged' : 'Flag';
        flagBtn.title = on ? 'You flagged this question. Click to remove the flag.'
                           : 'Flag this question to report a problem';
    }
    window.sppPaintFlag = paintFlag;

    if (flagBtn) {
        flagBtn.addEventListener('click', function () {
            var q = currentQuestion();
            if (!q) return;
            var next = !flagged[q.id];
            flagBtn.disabled = true;
            fetch('/api/test-flag/' + encodeURIComponent(testKey), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: q.id, flagged: next })
            })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d && d.success) {
                        flagged[q.id] = d.flagged;
                        paintFlag();
                    }
                })
                .catch(function () {})
                .finally(function () { flagBtn.disabled = false; });
        });
        setInterval(paintFlag, 700);
    }

    var fsBtn = document.getElementById('fullscreen-toggle-btn');
    if (fsBtn) {
        fsBtn.addEventListener('click', function () {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(function () {});
            } else {
                window.sppAllowFsExit = true;
                document.exitFullscreen().catch(function () {});
            }
        });
        document.addEventListener('fullscreenchange', function () {
            var icon = fsBtn.querySelector('i');
            if (icon) icon.className = document.fullscreenElement ? 'fas fa-compress' : 'fas fa-expand';
            fsBtn.title = document.fullscreenElement ? 'Exit Fullscreen' : 'Toggle Fullscreen';
        });
    }

    var qpBtn = document.getElementById('view-question-paper-btn');
    var qpModal = document.getElementById('question-paper-modal');
    var qpBody = document.getElementById('question-paper-body');
    var qpClose = document.getElementById('close-question-paper-btn');
    var qpLoaded = false;

    function esc(v) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }

    function renderPaper(questions) {
        if (!questions.length) {
            qpBody.innerHTML = '<p class="qp-loading">No questions available.</p>';
            return;
        }
        var section = '';
        var html = '<p class="qp-hint">Read-only view of the full paper. Answers are not saved here.</p>';
        questions.forEach(function (q) {
            if (q.section_name !== section) {
                section = q.section_name;
                html += '<h3 class="qp-sec">' + esc(section || 'Section') + '</h3>';
            }
            html += '<div class="qp-item"><div class="qp-item__head"><span class="qp-no">Q' + q.serial +
                '</span><span class="qp-type">' + esc(q.question_type) + '</span>' +
                '<span class="qp-marks">+' + esc(q.correct_marks) +
                (q.negative_marks ? ' / -' + esc(q.negative_marks) : '') + '</span></div>';
            if (q.question_image) {
                var src = q.question_image.charAt(0) === '/' ? q.question_image : '/' + q.question_image;
                html += '<div class="qp-img"><img src="' + esc(src) + '" alt="Question ' + q.serial + '"></div>';
            }
            if (q.question_text) html += '<div class="qp-text">' + q.question_text + '</div>';
            var opts = ['option_a', 'option_b', 'option_c', 'option_d']
                .map(function (k) { return q[k]; }).filter(Boolean);
            if (opts.length) {
                html += '<ol class="qp-opts" type="A">' +
                    opts.map(function (o) { return '<li>' + o + '</li>'; }).join('') + '</ol>';
            }
            html += '</div>';
        });
        qpBody.innerHTML = html;
    }

    function openPaper() {
        if (!qpModal) return;
        qpModal.style.display = 'block';
        if (qpLoaded) return;
        qpBody.innerHTML = '<p class="qp-loading">Loading question paper...</p>';
        fetch('/api/question-paper/' + encodeURIComponent(testKey))
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.error) {
                    qpBody.innerHTML = '<p class="qp-loading">' + esc(d.error) + '</p>';
                    return;
                }
                renderPaper(d.questions || []);
                qpLoaded = true;
            })
            .catch(function () {
                qpBody.innerHTML = '<p class="qp-loading">Could not load the question paper.</p>';
            });
    }

    function closePaper() {
        if (qpModal) qpModal.style.display = 'none';
    }

    if (qpBtn) qpBtn.addEventListener('click', openPaper);
    if (qpClose) qpClose.addEventListener('click', closePaper);
    if (qpModal) {
        qpModal.addEventListener('click', function (e) {
            if (e.target === qpModal) closePaper();
        });
    }
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closePaper();
    });

    window.sppRenderImageOptions = function (container, question, onPick, picked) {
        if (!question || !question.question_image || !question.option_regions) return false;
        var regions = question.option_regions;
        var keys = Object.keys(regions);
        if (!keys.length) return false;

        var wrap = document.createElement('div');
        wrap.className = 'qimg-wrap';
        var img = document.createElement('img');
        img.src = question.question_image.charAt(0) === '/' ? question.question_image
                                                           : '/' + question.question_image;
        img.alt = 'Question image';
        wrap.appendChild(img);

        keys.forEach(function (key) {
            var box = regions[key];
            var hot = document.createElement('div');
            hot.className = 'qimg-hot' + (picked === key.toUpperCase() ? ' is-picked' : '');
            hot.style.left = box.x + '%';
            hot.style.top = box.y + '%';
            hot.style.width = box.w + '%';
            hot.style.height = box.h + '%';
            hot.setAttribute('role', 'radio');
            hot.setAttribute('aria-label', 'Option ' + key.toUpperCase());
            hot.tabIndex = 0;
            var dot = document.createElement('span');
            dot.className = 'qimg-radio';
            hot.appendChild(dot);

            function choose() {
                wrap.querySelectorAll('.qimg-hot').forEach(function (n) { n.classList.remove('is-picked'); });
                hot.classList.add('is-picked');
                if (typeof onPick === 'function') onPick(key.toUpperCase());
            }
            hot.addEventListener('click', choose);
            hot.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choose(); }
            });
            wrap.appendChild(hot);
        });

        container.innerHTML = '';
        container.appendChild(wrap);
        return true;
    };
})();
