/* Quiz/assessment taking window.
 *
 * quiz mode:       picks are kept locally, everything grades at Submit.
 * assessment mode: each pick POSTs immediately; the server's reply (correct
 *                  option + explanation) drives the instant-feedback panel
 *                  and the options lock - there is no local answer key. */
(function () {
    'use strict';

    var CFG = window.QZ || {};
    var questions = CFG.questions || [];
    if (!questions.length) return;

    var index = 0;
    var maxSeen = 0;       // furthest question reached (assessment is forward-only)
    var picks = {};        // question_id -> 'A'..'D'
    var revealed = {};     // question_id -> server feedback (assessment)
    var finishing = false;

    var el = function (id) { return document.getElementById(id); };
    var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) { return { ok: res.ok, data: data }; });
        });
    }

    function esc(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    // ---------------- render one question ----------------
    function render() {
        if (index > maxSeen) maxSeen = index;
        var q = questions[index];
        el('qzQNum').textContent = 'Question ' + (index + 1) + ' of ' + questions.length;
        el('qzQText').textContent = q.question_text || '';
        var img = el('qzQImage');
        if (q.question_image) {
            img.src = q.question_image;
            img.classList.remove('is-hidden');
        } else {
            img.classList.add('is-hidden');
        }

        var host = el('qzOptions');
        host.innerHTML = ['A', 'B', 'C', 'D'].map(function (letter) {
            var text = q['option_' + letter.toLowerCase()];
            return '<button type="button" class="qz-opt" data-letter="' + letter + '">' +
                   '<span class="qz-opt__letter">' + letter + '</span>' +
                   '<span class="qz-opt__text">' + esc(text) + '</span>' +
                   '<i class="fas qz-opt__mark"></i></button>';
        }).join('');

        paintState(q);
        updateChrome();
    }

    function paintState(q) {
        var picked = picks[q.id];
        var feedback = revealed[q.id];
        var buttons = document.querySelectorAll('.qz-opt');
        buttons.forEach(function (btn) {
            var letter = btn.getAttribute('data-letter');
            btn.classList.toggle('is-picked', letter === picked && !feedback);
            if (feedback) {
                btn.disabled = true;
                btn.classList.toggle('is-correct', letter === feedback.correct_option);
                btn.classList.toggle('is-picked-wrong',
                    letter === picked && letter !== feedback.correct_option);
            } else {
                btn.disabled = false;
                btn.classList.remove('is-correct', 'is-picked-wrong');
            }
        });

        var panel = el('qzFeedback');
        if (feedback) {
            panel.classList.remove('is-hidden');
            panel.className = 'qz-feedback ' + (feedback.is_correct ? 'is-ok' : 'is-bad');
            panel.innerHTML =
                '<strong>' + (feedback.is_correct
                    ? '<i class="fas fa-check"></i> Correct!'
                    : '<i class="fas fa-xmark"></i> Wrong - the answer is ' +
                      esc(feedback.correct_option)) + '</strong>' +
                (feedback.explanation
                    ? '<p>' + esc(feedback.explanation) + '</p>' : '') +
                '<p class="qz-feedback__lock"><i class="fas fa-lock"></i> Answer locked.</p>';
        } else {
            panel.classList.add('is-hidden');
        }
    }

    function updateChrome() {
        el('qzProgressText').textContent = (index + 1) + ' / ' + questions.length;
        el('qzProgressBar').style.width = (100 * (index + 1) / questions.length) + '%';

        var last = index === questions.length - 1;
        var prev = el('qzPrev');
        // Assessment is strictly forward-only, like a real screening test.
        prev.classList.toggle('is-hidden', CFG.mode !== 'quiz' || index === 0);
        el('qzNext').classList.toggle('is-hidden', last);
        el('qzSubmit').classList.toggle('is-hidden', !last);

        var palette = el('qzPalette');
        if (palette) {
            palette.innerHTML = questions.map(function (q, i) {
                var classes = ['qz-pal'];
                if (i === index) classes.push('is-current');
                if (picks[q.id]) classes.push('is-answered');
                // Assessment is forward-only, so the navigator may revisit what
                // has already been reached but never skip ahead.
                var locked = CFG.mode !== 'quiz' && i > maxSeen;
                if (locked) classes.push('is-locked');
                return '<button type="button" class="' + classes.join(' ') +
                       '" data-jump="' + i + '"' +
                       (locked ? ' disabled aria-disabled="true" title="Not reached yet"' : '') +
                       '>' + (i + 1) + '</button>';
            }).join('');
        }
    }

    // ---------------- interactions ----------------
    el('qzOptions').addEventListener('click', function (e) {
        var btn = e.target.closest('.qz-opt');
        if (!btn || btn.disabled) return;
        var q = questions[index];
        var letter = btn.getAttribute('data-letter');

        if (CFG.mode === 'quiz') {
            picks[q.id] = letter;
            paintState(q);
            updateChrome();
            return;
        }

        // assessment: commit immediately, then reveal
        if (revealed[q.id]) return;
        picks[q.id] = letter;
        paintState(q);
        post(CFG.answerUrl, { attempt_id: CFG.attemptId, question_id: q.id, selected: letter })
            .then(function (r) {
                if (r.ok) {
                    revealed[q.id] = r.data;
                } else if (r.data.error === 'already_answered') {
                    revealed[q.id] = revealed[q.id] || { correct_option: '?', is_correct: false };
                } else {
                    delete picks[q.id];
                    alert(r.data.error || 'Could not save that answer. Try again.');
                }
                paintState(q);
            })
            .catch(function () {
                delete picks[q.id];
                paintState(q);
                alert('Network error - your answer was not saved. Pick again.');
            });
    });

    el('qzNext').addEventListener('click', function () {
        if (CFG.mode === 'assessment' && !revealed[questions[index].id]) {
            alert('Choose an option first - in assessment mode every question is answered in order.');
            return;
        }
        if (index < questions.length - 1) { index++; render(); }
    });
    el('qzPrev').addEventListener('click', function () {
        if (index > 0) { index--; render(); }
    });

    var palette = el('qzPalette');
    if (palette) {
        palette.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-jump]');
            if (!btn || btn.disabled) return;
            var target = parseInt(btn.getAttribute('data-jump'), 10);
            if (isNaN(target)) return;
            if (CFG.mode !== 'quiz' && target > maxSeen) return;
            index = target;
            render();
        });
    }

    el('qzSubmit').addEventListener('click', function () {
        if (finishing) return;
        var unanswered = questions.filter(function (q) { return !picks[q.id]; }).length;
        if (unanswered &&
            !confirm(unanswered + ' question(s) are unanswered and will count as skipped. Submit anyway?')) {
            return;
        }
        finishing = true;
        el('qzSubmit').disabled = true;
        var body = { attempt_id: CFG.attemptId };
        if (CFG.mode === 'quiz') body.answers = picks;
        post(CFG.finishUrl, body).then(function (r) {
            if (r.ok && r.data.success) {
                window.location.href = r.data.redirect;
            } else {
                alert(r.data.error || 'Could not submit. Try again.');
                finishing = false;
                el('qzSubmit').disabled = false;
            }
        }).catch(function () {
            alert('Network error. Try again.');
            finishing = false;
            el('qzSubmit').disabled = false;
        });
    });

    render();
}());

(function () {
    var timerEl = document.getElementById('qzTimer');
    var numBox = document.getElementById('qzNumBox');
    var subProg = document.getElementById('qzSubProgress');
    var progText = document.getElementById('qzProgressText');
    var btn = document.getElementById('qzPaletteBtn');
    var panel = document.getElementById('qzPalettePanel');

    if (timerEl) {
        var t0 = Date.now();
        setInterval(function () {
            var s = Math.floor((Date.now() - t0) / 1000);
            var m = Math.floor(s / 60);
            var h = Math.floor(m / 60);
            var mm = String(m % 60).padStart(2, '0');
            var ss = String(s % 60).padStart(2, '0');
            timerEl.textContent = (h ? h + ':' : '') + mm + ':' + ss;
        }, 1000);
    }

    function syncNum() {
        if (!progText) return;
        var parts = (progText.textContent || '').split('/');
        if (numBox && parts[0]) numBox.textContent = parts[0].trim();
        if (subProg) subProg.textContent = (progText.textContent || '').trim();
    }

    if (progText) {
        syncNum();
        new MutationObserver(syncNum).observe(progText, { childList: true, characterData: true, subtree: true });
    }

    if (btn && panel) {
        var backdrop = document.createElement('div');
        backdrop.className = 'qz-palette-backdrop is-hidden';
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);

        // Panel and backdrop must open and close together. Closing only the
        // panel used to leave the full-screen backdrop behind, which swallowed
        // every later click and made the navigator look broken.
        function setPanelOpen(open) {
            panel.classList.toggle('is-hidden', !open);
            backdrop.classList.toggle('is-hidden', !open);
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (!open) return;
            var total = panel.querySelectorAll('.qz-pal').length;
            var done = panel.querySelectorAll('.qz-pal.is-answered').length;
            var count = document.getElementById('qzNavCount');
            if (count) count.textContent = done + ' / ' + total + ' answered';
            var cur = panel.querySelector('.qz-pal.is-current');
            if (cur) cur.scrollIntoView({ block: 'nearest' });
        }

        backdrop.addEventListener('click', function () { setPanelOpen(false); });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !panel.classList.contains('is-hidden')) setPanelOpen(false);
        });

        var head = panel.querySelector('.qz-palette-panel__head');
        if (head) {
            var closeX = document.createElement('button');
            closeX.type = 'button';
            closeX.className = 'qz-palette-close';
            closeX.setAttribute('aria-label', 'Close navigator');
            closeX.innerHTML = '&times;';
            closeX.addEventListener('click', function () { setPanelOpen(false); });
            head.appendChild(closeX);
        }

        var nextBtn = document.getElementById('qzNext');
        if (nextBtn) {
            nextBtn.addEventListener('click', function (e) {
                var answered = document.querySelector('.qz-opt.is-picked') ||
                               document.querySelector('.qz-opt:disabled') ||
                               document.querySelector('.qz-opt.is-correct, .qz-opt.is-wrong');
                if (!answered) {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                    var fb = document.getElementById('qzFeedback');
                    if (fb) {
                        fb.className = 'qz-feedback is-bad';
                        fb.textContent = 'Choose an option before moving to the next question.';
                        setTimeout(function () { fb.classList.add('is-hidden'); }, 2500);
                    }
                }
            }, true);
        }

        btn.addEventListener('click', function () {
            setPanelOpen(panel.classList.contains('is-hidden'));
        });

        panel.addEventListener('click', function (e) {
            // Picking a question closes the navigator. The close button and the
            // panel chrome are handled by their own listeners.
            if (e.target.closest('[data-jump], .qz-dot, [data-q]')) setPanelOpen(false);
        });
    }
})();

(function () {
    document.addEventListener('keydown', function (e) {
        if (e.target.matches('input, textarea, select')) return;
        if (e.altKey || e.ctrlKey || e.metaKey) return;

        if (e.key >= '1' && e.key <= '9') {
            var opts = document.querySelectorAll('.qz-opt:not(:disabled)');
            var pick = opts[Number(e.key) - 1];
            if (pick) { e.preventDefault(); pick.click(); }
            return;
        }
        if (e.key === 'Enter') {
            var next = document.getElementById('qzNext');
            var submit = document.getElementById('qzSubmit');
            var target = (next && !next.classList.contains('is-hidden')) ? next
                       : (submit && !submit.classList.contains('is-hidden')) ? submit : null;
            if (target) { e.preventDefault(); target.click(); }
            return;
        }
        if (e.key === 'p' || e.key === 'P') {
            var btn = document.getElementById('qzPaletteBtn');
            if (btn) { e.preventDefault(); btn.click(); }
        }
    });
})();
