'use strict';
const QUESTIONS_PER_PAGE = 5;
const SESSION_KEY_PREFIX  = 'pq_v3_';

let correctCount   = 0;
let incorrectCount = 0;
let currentPage    = 1;
let totalPages     = 1;

const storedExplanations = {};
const answeredQuestions  = new Set();
const userSelectedOptions = {};

let globalTimerInterval = null;
let globalTimerSeconds  = 0;
let globalTimerEnabled  = false;
let timerExpired        = false;
let isQuizMode          = false;
let quizSubmitted       = false;
let sessionGen          = 0;

function getUserIdentity() {
    try {
        const meta = document.getElementById('user-identity-meta');
        return meta ? (meta.getAttribute('content') || 'guest') : 'guest';
    } catch { return 'guest'; }
}

function getSessionKey() {
    try {
        const path = btoa(encodeURIComponent(window.location.pathname)).replace(/=/g, '');
        const uid  = btoa(encodeURIComponent(getUserIdentity())).replace(/=/g, '');
        return SESSION_KEY_PREFIX + uid + '_' + path;
    } catch {
        return SESSION_KEY_PREFIX + window.location.pathname.replace(/\W/g, '_');
    }
}

function buildEmptySession() {
    return {
        answered: {},
        scores: { correct: 0, incorrect: 0 },
        timerSecondsLeft: 0,
        timerSavedAt: 0,
        timerEnabled: false,
        selectedOptions: {},
        isQuizMode: false,
        quizSubmitted: false
    };
}

function loadSession() {
    try {
        const raw = localStorage.getItem(getSessionKey());
        return raw ? JSON.parse(raw) : buildEmptySession();
    } catch { return buildEmptySession(); }
}

function saveSession(data) {
    try { localStorage.setItem(getSessionKey(), JSON.stringify(data)); } catch {}
}

function clearSession() {
    try { localStorage.removeItem(getSessionKey()); } catch {}
}

function persistAnswer(qId, resultData) {
    const s = loadSession();
    s.answered[qId] = {
        is_correct:     resultData.is_correct,
        correct_option: resultData.correct_option,
        answer_text:    resultData.answer_text || 'No explanation available.',
        user_selected:  userSelectedOptions[qId] !== undefined ? userSelectedOptions[qId] : null
    };
    if (resultData.is_correct) {
        s.scores.correct = (s.scores.correct || 0) + 1;
    } else {
        s.scores.incorrect = (s.scores.incorrect || 0) + 1;
    }
    delete s.selectedOptions[qId];
    if (globalTimerEnabled) {
        s.timerSecondsLeft = globalTimerSeconds;
        s.timerSavedAt     = Date.now();
    }
    saveSession(s);
}

function persistSelectedOption(qId, value) {
    userSelectedOptions[qId] = value;
    try {
        const s = loadSession();
        if (!s.selectedOptions) s.selectedOptions = {};
        s.selectedOptions[qId] = value;
        saveSession(s);
    } catch {}
}

function persistTimerState() {
    if (!globalTimerEnabled) return;
    try {
        const s = loadSession();
        s.timerSecondsLeft = globalTimerSeconds;
        s.timerSavedAt     = Date.now();
        s.timerEnabled     = true;
        saveSession(s);
    } catch {}
}

function formatTime(seconds) {
    const s   = Math.max(0, Math.round(seconds));
    const m   = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return m + ':' + sec;
}

function startGlobalTimer(totalSeconds) {
    globalTimerSeconds = Math.max(0, Math.round(totalSeconds));
    globalTimerEnabled = true;
    timerExpired       = false;
    updateGlobalTimerDisplay();

    const wrap = document.getElementById('global-timer-wrap');
    if (wrap) wrap.style.display = 'flex';

    clearInterval(globalTimerInterval);
    globalTimerInterval = setInterval(function () {
        globalTimerSeconds--;
        updateGlobalTimerDisplay();
        if (globalTimerSeconds % 5 === 0) persistTimerState();
        if (globalTimerSeconds <= 0) {
            clearInterval(globalTimerInterval);
            onGlobalTimerExpired();
        }
    }, 1000);
}

function updateGlobalTimerDisplay() {
    const el   = document.getElementById('global-timer-display');
    const wrap = document.getElementById('global-timer-wrap');
    if (el) el.textContent = formatTime(globalTimerSeconds);
    if (!wrap) return;
    wrap.classList.remove('gt-warning', 'gt-danger');
    if (globalTimerSeconds <= 60)       wrap.classList.add('gt-danger');
    else if (globalTimerSeconds <= 180) wrap.classList.add('gt-warning');
}

function stopGlobalTimer() {
    clearInterval(globalTimerInterval);
    globalTimerEnabled = false;
}

function lockAllUnansweredInputs() {
    document.querySelectorAll('.question-card').forEach(function (card) {
        const qId = card.id.replace('question-', '');
        if (answeredQuestions.has(qId)) return;
        const form = document.getElementById('form-' + qId);
        if (form) {
            form.querySelectorAll('input').forEach(function (inp) { inp.disabled = true; });
            form.querySelectorAll('.option-row').forEach(function (row) { row.classList.add('locked'); });
        }
        const submitBtn = document.getElementById('submit-' + qId);
        if (submitBtn) submitBtn.style.display = 'none';
    });
}

function onGlobalTimerExpired() {
    timerExpired = true;
    const el = document.getElementById('global-timer-display');
    if (el) el.textContent = '00:00';
    lockAllUnansweredInputs();

    if (isQuizMode && !quizSubmitted) {
        submitQuiz(true);
        return;
    }
    buildTimerExpiredReview(function (stats) {
        showTimerExpiredPopup(stats);
    });
}

function buildTimerExpiredReview(callback) {
    var allCards = document.querySelectorAll('.question-card');
    var totalQ   = allCards.length;
    var attempted  = 0, skipped = 0, correct = 0, incorrect = 0;
    var fetchPromises = [];
    var s = loadSession();
    var capturedGen = sessionGen;

    allCards.forEach(function (card) {
        var qId     = card.id.replace('question-', '');
        var qType   = getQuestionType(card);
        var form    = document.getElementById('form-' + qId);

        if (answeredQuestions.has(qId)) {
            var saved = s.answered[qId];
            if (saved && saved.is_correct) correct++; else incorrect++;
            attempted++;
            return;
        }

        var selected = form ? getSelectedAnswer(qId, qType, form) : null;

        if (selected === null) {
            skipped++;
            revealCorrectOptionOnly(qId, qType, null);
        } else {
            attempted++;
            var promise = fetch('/check_answer/' + qId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_option: selected })
            })
            .then(function (r) {
                if (!r.ok) throw new Error('Server error ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (capturedGen !== sessionGen) return;
                if (data.error) { skipped++; attempted--; revealCorrectOptionOnly(qId, qType, null); return; }
                if (data.is_correct) correct++; else incorrect++;
                storedExplanations[qId] = (data.answer_text && data.answer_text.trim())
                    ? data.answer_text : 'No explanation available.';
                answeredQuestions.add(qId);
                revealCorrectOptionOnly(qId, qType, {
                    selected: selected,
                    correct_option: data.correct_option,
                    is_correct: data.is_correct
                });
                persistAnswer(qId, data);
            })
            .catch(function () {
                if (capturedGen !== sessionGen) return;
                skipped++;
                attempted--;
                revealCorrectOptionOnly(qId, qType, null);
            });
            fetchPromises.push(promise);
        }
    });

    Promise.allSettled(fetchPromises).then(function () {
        if (capturedGen !== sessionGen) return;
        correctCount   = correct;
        incorrectCount = incorrect;
        var scoreEl = document.getElementById('correct-count');
        var wrongEl = document.getElementById('incorrect-count');
        if (scoreEl) scoreEl.textContent = correct;
        if (wrongEl) wrongEl.textContent = incorrect;
        if (typeof callback === 'function') {
            callback({ total: totalQ, attempted: attempted, skipped: skipped, correct: correct, incorrect: incorrect });
        }
    });
}

function revealCorrectOptionOnly(qId, qType, resultInfo) {
    const card = document.getElementById('question-' + qId);
    if (!card) return;
    const form = document.getElementById('form-' + qId);

    if (qType === 'NAT') {
        const input = document.getElementById('nat-' + qId);
        if (input) input.disabled = true;
        const submitBtn = document.getElementById('submit-' + qId);
        if (submitBtn) submitBtn.style.display = 'none';

        const natWrap = card.querySelector('.nat-wrap');
        if (natWrap && resultInfo) {
            const existing = natWrap.querySelector('.nat-reveal');
            if (existing) existing.remove();

            const tag = document.createElement('div');
            tag.className = resultInfo.is_correct ? 'nat-reveal correct' : 'nat-reveal incorrect';
            tag.innerHTML = resultInfo.is_correct
                ? '<i class="fas fa-check-circle"></i> Correct! You entered the right answer.'
                : '<i class="fas fa-times-circle"></i> Correct Answer: <strong>' + escapeHtml(String(resultInfo.correct_option)) + '</strong>';
            natWrap.appendChild(tag);
        }
        markQuestionStatus(qId, resultInfo ? (resultInfo.is_correct ? 'correct' : 'incorrect') : 'skipped');
        return;
    }

    if (form) {
        form.querySelectorAll('input').forEach(function (inp) { inp.disabled = true; });
    }
    const submitBtn = document.getElementById('submit-' + qId);
    if (submitBtn) submitBtn.style.display = 'none';

    if (!resultInfo) {
        markQuestionStatus(qId, 'skipped');
        return;
    }

    const correctOpts = String(resultInfo.correct_option || '')
        .split(',')
        .map(function (c) { return c.trim().toUpperCase(); })
        .filter(Boolean);

    const selectedArr = Array.isArray(resultInfo.selected)
        ? resultInfo.selected.map(function (v) { return String(v).trim().toUpperCase(); })
        : [String(resultInfo.selected || '').trim().toUpperCase()];

    if (form) {
        form.querySelectorAll('.option-row').forEach(function (row) {
            row.classList.add('locked');
            const inp = row.querySelector('input');
            if (!inp) return;

            const val        = String(inp.value || '').trim().toUpperCase();
            const isCorrect  = correctOpts.indexOf(val) !== -1;
            const wasChosen  = selectedArr.indexOf(val) !== -1;

            row.classList.remove('reveal-correct', 'reveal-wrong', 'reveal-correct-unchosen');

            const oldLabel = row.querySelector('.opt-annotation');
            if (oldLabel) oldLabel.remove();

            const optStatus = row.querySelector('.opt-status');

            if (isCorrect && wasChosen) {

                row.classList.add('reveal-correct');
                if (optStatus) {
                    optStatus.style.display = 'flex';
                    optStatus.innerHTML = '<i class="fas fa-check-circle"></i>';
                    optStatus.title = 'You chose this - Correct!';
                }
                appendOptAnnotation(row, 'you-correct', 'You chose · Correct');

            } else if (wasChosen && !isCorrect) {

                row.classList.add('reveal-wrong');
                if (optStatus) {
                    optStatus.style.display = 'flex';
                    optStatus.innerHTML = '<i class="fas fa-times-circle"></i>';
                    optStatus.title = 'You chose this - Wrong';
                }
                appendOptAnnotation(row, 'you-wrong', 'Your choice · Wrong');

            } else if (isCorrect && !wasChosen) {

                row.classList.add('reveal-correct-unchosen');
                if (optStatus) {
                    optStatus.style.display = 'flex';
                    optStatus.innerHTML = '<i class="fas fa-check-circle"></i>';
                    optStatus.title = 'Correct answer';
                }
                appendOptAnnotation(row, 'correct-ans', 'Correct Answer');
            }
        });
    }

    markQuestionStatus(qId, resultInfo.is_correct ? 'correct' : 'incorrect');
}

function appendOptAnnotation(row, type, text) {
    const span = document.createElement('span');
    span.className = 'opt-annotation opt-annotation--' + type;
    span.textContent = text;
    row.appendChild(span);
}

function markQuestionStatus(qId, status) {
    const badge = document.getElementById('q-status-badge-' + qId);
    if (!badge) return;
    badge.classList.remove('badge-attempted', 'badge-skipped', 'badge-correct', 'badge-incorrect', 'badge-not-attempted');

    switch (status) {
        case 'correct':
            badge.innerHTML = '<i class="fas fa-check-circle"></i> Correct';
            badge.classList.add('badge-correct');
            break;
        case 'incorrect':
            badge.innerHTML = '<i class="fas fa-times-circle"></i> Incorrect';
            badge.classList.add('badge-incorrect');
            break;
        case 'not-attempted':
            badge.innerHTML = '<i class="fas fa-minus-circle"></i> Not Attempted';
            badge.classList.add('badge-not-attempted');
            break;
        default:
            badge.innerHTML = '<i class="fas fa-circle-minus"></i> Skipped';
            badge.classList.add('badge-skipped');
    }
    badge.style.display = 'inline-flex';
}

function showTimerExpiredPopup(stats) {
    const overlay = document.getElementById('timer-expired-overlay');
    if (!overlay) return;
    const safe = function (id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    safe('te-total',     stats.total);
    safe('te-attempted', stats.attempted);
    safe('te-skipped',   stats.skipped);
    safe('te-correct',   stats.correct);
    safe('te-incorrect', stats.incorrect);
    overlay.classList.add('open');
}

function closeTimerExpiredPopup() {
    const overlay = document.getElementById('timer-expired-overlay');
    if (overlay) overlay.classList.remove('open');
    const allCards = document.querySelectorAll('.question-card');
    totalPages = Math.ceil(allCards.length / QUESTIONS_PER_PAGE);
    goToPage(1);
}

function getSelectedAnswer(qId, qType, form) {
    if (qType === 'NAT') {
        const input = document.getElementById('nat-' + qId);
        const val   = input ? input.value.trim() : '';
        return val || null;
    }
    if (qType === 'MSQ') {
        const checked = Array.from(form.querySelectorAll('input[type="checkbox"]:checked'))
            .map(function (cb) { return cb.value; });
        return checked.length ? checked : null;
    }
    const radio = form.querySelector('input[type="radio"]:checked');
    return radio ? radio.value : null;
}

function getQuestionType(cardEl) {
    const tag = cardEl.querySelector('.q-type-tag');
    return tag ? tag.textContent.trim().toUpperCase() : 'MCQ';
}

function lockQuestion(qId, qType, form) {
    answeredQuestions.add(qId);
    if (qType === 'NAT') {
        const input = document.getElementById('nat-' + qId);
        if (input) input.disabled = true;
    } else {
        if (form) {
            form.querySelectorAll('input').forEach(function (inp) { inp.disabled = true; });
        }
    }
    if (form) {
        form.querySelectorAll('.option-row').forEach(function (row) { row.classList.add('locked'); });
    }
}

function showInlineError(qId, message) {
    const existing = document.getElementById('inline-error-' + qId);
    if (existing) existing.remove();
    const el = document.createElement('div');
    el.id        = 'inline-error-' + qId;
    el.className = 'inline-error-msg';
    el.setAttribute('role', 'alert');
    el.textContent = message;
    const footer = document.querySelector('#form-' + qId + ' .q-footer');
    if (footer) footer.insertAdjacentElement('beforebegin', el);
    setTimeout(function () { if (el.parentNode) el.remove(); }, 4000);
}

function submitAnswer(event, qId, qType) {
    event.preventDefault();

    if (answeredQuestions.has(qId)) return;
    if (timerExpired)               return;
    if (isQuizMode)                 return;

    const form = document.getElementById('form-' + qId);
    if (!form) return;

    const selected = getSelectedAnswer(qId, qType, form);
    if (selected === null) {
        const msg = qType === 'MSQ'
            ? 'Please select at least one option.'
            : qType === 'NAT'
            ? 'Please enter a numeric answer.'
            : 'Please select an option.';
        showInlineError(qId, msg);
        return;
    }

    userSelectedOptions[qId] = selected;
    submitAnswerCore(qId, qType, selected, form);
}

function submitAnswerCore(qId, qType, selected, form) {
    if (answeredQuestions.has(qId)) return;

    var capturedGen = sessionGen;
    var submitBtn = document.getElementById('submit-' + qId);
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Checking...';
    }

    fetch('/check_answer/' + qId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_option: selected })
    })
    .then(function (response) {
        if (!response.ok) throw new Error('Server error ' + response.status);
        return response.json();
    })
    .then(function (data) {
        if (capturedGen !== sessionGen) return;
        if (data.error) {
            showInlineError(qId, data.error);
            var btn = document.getElementById('submit-' + qId);
            if (btn) { btn.disabled = false; btn.innerHTML = 'Submit Answer'; }
            return;
        }
        storedExplanations[qId] = (data.answer_text && data.answer_text.trim())
            ? data.answer_text : 'No explanation available.';
        lockQuestion(qId, qType, form);
        var btn = document.getElementById('submit-' + qId);
        if (btn) btn.style.display = 'none';
        showResult(qId, data);
        updateScore(data.is_correct);
        persistAnswer(qId, data);
        markQuestionStatus(qId, data.is_correct ? 'correct' : 'incorrect');
        checkAllAnswered();
    })
    .catch(function () {
        if (capturedGen !== sessionGen) return;
        showInlineError(qId, 'Network error. Please try again.');
        var btn = document.getElementById('submit-' + qId);
        if (btn) { btn.disabled = false; btn.innerHTML = 'Submit Answer'; }
    });
}

function showResult(qId, data) {
    const card    = document.getElementById('question-' + qId);
    const banner  = document.getElementById('result-banner-' + qId);
    const actions = document.getElementById('result-actions-' + qId);
    const toggleBtn = document.getElementById('toggle-btn-' + qId);
    if (!card || !banner || !actions) return;

    card.classList.remove('answered-correct', 'answered-incorrect');
    card.classList.add(data.is_correct ? 'answered-correct' : 'answered-incorrect');

    banner.className = 'result-banner ' + (data.is_correct ? 'correct-msg' : 'incorrect-msg');
    banner.setAttribute('role', 'status');

    const qType   = getQuestionType(card);
    const form    = document.getElementById('form-' + qId);
    const selected = userSelectedOptions[qId];

    if (data.is_correct) {
        const chosenLabel = buildChosenLabel(selected, qType);
        banner.innerHTML  =
            '<i class="fas fa-check-circle" aria-hidden="true"></i> ' +
            '<span>Correct! ' + chosenLabel + '</span>';
    } else {
        const correctStr  = data.correct_option ? escapeHtml(String(data.correct_option)) : 'N/A';
        const chosenLabel = buildChosenLabel(selected, qType);
        banner.innerHTML  =
            '<i class="fas fa-times-circle" aria-hidden="true"></i>' +
            '<span>' + chosenLabel + ' - Correct Answer: <strong>' + correctStr + '</strong></span>';
    }


    applyOptionReveal(qId, qType, form, selected, data.correct_option, data.is_correct);

    actions.style.display = 'flex';
    if (toggleBtn) toggleBtn.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i> Show Solution';
}

function showResultFromCache(qId, data) {
    const card    = document.getElementById('question-' + qId);
    const banner  = document.getElementById('result-banner-' + qId);
    const actions = document.getElementById('result-actions-' + qId);
    const toggleBtn = document.getElementById('toggle-btn-' + qId);
    if (!card || !banner || !actions) return;

    card.classList.remove('answered-correct', 'answered-incorrect');
    card.classList.add(data.is_correct ? 'answered-correct' : 'answered-incorrect');

    banner.className = 'result-banner ' + (data.is_correct ? 'correct-msg' : 'incorrect-msg');
    banner.setAttribute('role', 'status');

    const qType    = getQuestionType(card);
    const form     = document.getElementById('form-' + qId);
    const selected = data.user_selected;

    if (data.is_correct) {
        const chosenLabel = buildChosenLabel(selected, qType);
        banner.innerHTML  =
            '<i class="fas fa-check-circle" aria-hidden="true"></i> ' +
            '<span>Correct! ' + chosenLabel + '</span>';
    } else {
        const correctStr  = data.correct_option ? escapeHtml(String(data.correct_option)) : 'N/A';
        const chosenLabel = buildChosenLabel(selected, qType);
        banner.innerHTML  =
            '<i class="fas fa-times-circle" aria-hidden="true"></i>' +
            '<span>' + chosenLabel + ' - Correct Answer: <strong>' + correctStr + '</strong></span>';
    }

    applyOptionReveal(qId, qType, form, selected, data.correct_option, data.is_correct);

    actions.style.display = 'flex';
    if (toggleBtn) toggleBtn.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i> Show Solution';
}

function showUnattemptedResult(qId) {
    const card    = document.getElementById('question-' + qId);
    const banner  = document.getElementById('result-banner-' + qId);
    const actions = document.getElementById('result-actions-' + qId);
    if (!card || !banner) return;

    card.classList.add('answered-not-attempted');
    banner.className = 'result-banner not-attempted-msg';
    banner.setAttribute('role', 'status');
    banner.innerHTML = '<i class="fas fa-minus-circle" aria-hidden="true"></i> Not Attempted - Solution shown below';

    if (actions) actions.style.display = 'flex';
    markQuestionStatus(qId, 'not-attempted');


    const qType = getQuestionType(card);
    const form  = document.getElementById('form-' + qId);

    fetch('/check_answer/' + qId + '?reveal=1', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_option: null, reveal_only: true })
    })
    .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
    .then(function (data) {
        if (!data.correct_option) return;
        storedExplanations[qId] = (data.answer_text && data.answer_text.trim())
            ? data.answer_text : 'No explanation available.';

        applyOptionReveal(qId, qType, form, null, data.correct_option, false);

        banner.innerHTML =
            '<i class="fas fa-minus-circle" aria-hidden="true"></i>' +
            ' Not Attempted - Correct Answer: <strong>' + escapeHtml(String(data.correct_option)) + '</strong>';
    })
    .catch(function () {
    });
}


function applyOptionReveal(qId, qType, form, selected, correctOption, isCorrect) {
    if (!form || qType === 'NAT') return;

    const correctOpts = String(correctOption || '')
        .split(',')
        .map(function (c) { return c.trim().toUpperCase(); })
        .filter(Boolean);

    const selectedArr = selected === null || selected === undefined
        ? []
        : Array.isArray(selected)
            ? selected.map(function (v) { return String(v).trim().toUpperCase(); })
            : [String(selected).trim().toUpperCase()];

    form.querySelectorAll('.option-row').forEach(function (row) {
        row.classList.add('locked');
        const inp = row.querySelector('input');
        if (!inp) return;

        const val       = String(inp.value || '').trim().toUpperCase();
        const isCorr    = correctOpts.indexOf(val) !== -1;
        const wasChosen = selectedArr.indexOf(val) !== -1;

        row.classList.remove('reveal-correct', 'reveal-wrong', 'reveal-correct-unchosen');
        const oldAnnotation = row.querySelector('.opt-annotation');
        if (oldAnnotation) oldAnnotation.remove();
        const optStatus = row.querySelector('.opt-status');

        if (isCorr && wasChosen) {

            row.classList.add('reveal-correct');
            if (optStatus) {
                optStatus.style.display = 'flex';
                optStatus.innerHTML = '<i class="fas fa-check-circle"></i>';
            }
            appendOptAnnotation(row, 'you-correct', 'You chose · Correct');

        } else if (wasChosen && !isCorr) {

            row.classList.add('reveal-wrong');
            if (optStatus) {
                optStatus.style.display = 'flex';
                optStatus.innerHTML = '<i class="fas fa-times-circle"></i>';
            }
            appendOptAnnotation(row, 'you-wrong', 'Your choice · Wrong');

        } else if (isCorr && !wasChosen) {
            row.classList.add('reveal-correct-unchosen');
            if (optStatus) {
                optStatus.style.display = 'flex';
                optStatus.innerHTML = '<i class="fas fa-check-circle"></i>';
            }
            appendOptAnnotation(row, 'correct-ans', 'Correct Answer');
        }
    });
}

function buildChosenLabel(selected, qType) {
    if (!selected) return '';
    if (Array.isArray(selected)) {
        return '(You chose: ' + selected.map(escapeHtml).join(', ') + ')';
    }
    return '(You chose: ' + escapeHtml(String(selected)) + ')';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function checkAllAnswered() {
    if (isQuizMode) return;
    const allCards = document.querySelectorAll('.question-card');
    const allDone  = Array.from(allCards).every(function (c) {
        return answeredQuestions.has(c.id.replace('question-', ''));
    });
    if (allDone) {
        stopGlobalTimer();
        showSessionCompletePopup();
    }
}

function showSessionCompletePopup() {
    const overlay = document.getElementById('session-complete-overlay');
    if (!overlay) return;
    const safe = function (id, val) { const el = document.getElementById(id); if (el) el.textContent = val; };
    safe('sc-correct',   correctCount);
    safe('sc-incorrect', incorrectCount);
    safe('sc-total',     correctCount + incorrectCount);
    overlay.classList.add('open');
}

function updateScore(isCorrect) {
    if (isCorrect) {
        correctCount++;
        const el = document.getElementById('correct-count');
        if (el) el.textContent = correctCount;
    } else {
        incorrectCount++;
        const el = document.getElementById('incorrect-count');
        if (el) el.textContent = incorrectCount;
    }
}

function resetSession() {
    sessionGen++;
    clearSession();

    correctCount   = 0;
    incorrectCount = 0;
    currentPage    = 1;
    totalPages     = 1;
    timerExpired   = false;
    isQuizMode     = false;
    quizSubmitted  = false;

    answeredQuestions.clear();
    Object.keys(storedExplanations).forEach(function (k) { delete storedExplanations[k]; });
    Object.keys(userSelectedOptions).forEach(function (k) { delete userSelectedOptions[k]; });

    stopGlobalTimer();
    globalTimerEnabled = false;
    globalTimerSeconds = 0;

    const correctEl   = document.getElementById('correct-count');
    const incorrectEl = document.getElementById('incorrect-count');
    if (correctEl)   correctEl.textContent   = '0';
    if (incorrectEl) incorrectEl.textContent = '0';

    const timerWrap = document.getElementById('global-timer-wrap');
    if (timerWrap) {
        timerWrap.style.display = 'none';
        timerWrap.classList.remove('gt-warning', 'gt-danger');
    }
    const timerDisplay = document.getElementById('global-timer-display');
    if (timerDisplay) timerDisplay.textContent = '00:00';


    ['timer-expired-overlay', 'session-complete-overlay', 'quiz-summary-overlay'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('open');
    });


    const paginationWrap = document.getElementById('pagination-wrap');
    if (paginationWrap) { paginationWrap.style.display = ''; paginationWrap.innerHTML = ''; }

    const quizBar = document.getElementById('quiz-bottom-bar');
    if (quizBar) quizBar.style.display = 'none';

    const quizFinalBtn = document.getElementById('quiz-final-submit-btn');
    if (quizFinalBtn) {
        quizFinalBtn.disabled  = false;
        quizFinalBtn.innerHTML = '<i class="fas fa-paper-plane" aria-hidden="true"></i> Submit Quiz';
    }

    document.body.classList.remove('quiz-mode-active');

    document.querySelectorAll('.question-card').forEach(function (card) {
        card.classList.remove('answered-correct', 'answered-incorrect', 'answered-not-attempted');
        card.style.display = '';
        const qId = card.id.replace('question-', '');

        const form = document.getElementById('form-' + qId);
        if (form) {
            form.querySelectorAll('input').forEach(function (inp) {
                inp.disabled = false;
                inp.checked  = false;
                if (inp.type === 'number' || inp.type === 'text') inp.value = '';
            });
            form.querySelectorAll('.option-row').forEach(function (row) {
                row.classList.remove(
                    'locked', 'selected',
                    'reveal-correct', 'reveal-wrong', 'reveal-correct-unchosen'
                );

                const ann = row.querySelector('.opt-annotation');
                if (ann) ann.remove();

                const optStatus = row.querySelector('.opt-status');
                if (optStatus) { optStatus.style.display = 'none'; optStatus.innerHTML = '<i class="fas fa-check-circle"></i>'; }
            });
        }

        const submitBtn = document.getElementById('submit-' + qId);
        if (submitBtn) {
            submitBtn.style.display   = '';
            submitBtn.disabled        = false;
            submitBtn.innerHTML       = 'Submit Answer';
            submitBtn.removeAttribute('data-submitted');
        }

        const banner = document.getElementById('result-banner-' + qId);
        if (banner) { banner.className = ''; banner.innerHTML = ''; }

        const actions = document.getElementById('result-actions-' + qId);
        if (actions) actions.style.display = 'none';

        const panel = document.getElementById('explanation-' + qId);
        if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }


        const err = document.getElementById('inline-error-' + qId);
        if (err) err.remove();


        const badge = document.getElementById('q-status-badge-' + qId);
        if (badge) { badge.textContent = ''; badge.className = 'q-status-badge'; badge.style.display = 'none'; }


        card.querySelectorAll('.nat-reveal').forEach(function (el) { el.remove(); });
    });

    openPreSessionPopup();
}

function toggleExplanation(qId) {
    const panel = document.getElementById('explanation-' + qId);
    const btn   = document.getElementById('toggle-btn-' + qId);
    if (!panel || !btn) return;

    const isHidden = panel.style.display === 'none' || panel.style.display === '';
    if (isHidden) {
        const explanation = storedExplanations[qId] || 'No explanation available.';
        panel.innerHTML =
            '<div class="explanation-panel">' +
                '<div class="exp-title"><i class="fas fa-lightbulb" aria-hidden="true"></i> SOLUTION &amp; EXPLANATION</div>' +
                '<div class="exp-content">' + explanation + '</div>' +
            '</div>';
        panel.style.display = 'block';
        btn.innerHTML = '<i class="fas fa-eye-slash" aria-hidden="true"></i> Hide Solution';
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        panel.style.display = 'none';
        btn.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i> Show Solution';
    }
}

function submitQuiz(autoExpired) {
    if (quizSubmitted) return;
    quizSubmitted = true;
    stopGlobalTimer();

    var capturedGen = sessionGen;
    var mainSubmitBtn = document.getElementById('quiz-final-submit-btn');
    if (mainSubmitBtn) {
        mainSubmitBtn.disabled = true;
        mainSubmitBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Submitting...';
    }

    var allCards  = document.querySelectorAll('.question-card');
    var totalQ    = allCards.length;
    var attempted   = 0;
    var unattempted = 0;
    var correct     = 0;
    var incorrect   = 0;

    var fetchPromises = [];
    var s = loadSession();

    allCards.forEach(function (card) {
        var qId   = card.id.replace('question-', '');
        var qType = getQuestionType(card);
        var form  = document.getElementById('form-' + qId);

        if (answeredQuestions.has(qId)) {
            var saved = s.answered[qId];
            if (saved && saved.is_correct) correct++; else incorrect++;
            attempted++;
            return;
        }

        var selected = form ? getSelectedAnswer(qId, qType, form) : null;

        if (selected === null) {
            unattempted++;
            lockQuestion(qId, qType, form);
            var btn0 = document.getElementById('submit-' + qId);
            if (btn0) btn0.style.display = 'none';
            showUnattemptedResult(qId);
        } else {
            attempted++;
            var promise = fetch('/check_answer/' + qId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_option: selected })
            })
            .then(function (r) {
                if (!r.ok) throw new Error('Server error ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (capturedGen !== sessionGen) return;
                if (data.error) {
                    unattempted++;
                    attempted--;
                    lockQuestion(qId, qType, form);
                    showUnattemptedResult(qId);
                    return;
                }
                if (data.is_correct) correct++; else incorrect++;
                storedExplanations[qId] = (data.answer_text && data.answer_text.trim())
                    ? data.answer_text : 'No explanation available.';
                lockQuestion(qId, qType, form);
                var btn = document.getElementById('submit-' + qId);
                if (btn) btn.style.display = 'none';
                userSelectedOptions[qId] = selected;
                showResult(qId, data);
                persistAnswer(qId, data);
            })
            .catch(function () {
                if (capturedGen !== sessionGen) return;
                unattempted++;
                attempted--;
                showUnattemptedResult(qId);
            });
            fetchPromises.push(promise);
        }
    });

    Promise.allSettled(fetchPromises).then(function () {
        if (capturedGen !== sessionGen) return;
        correctCount   = correct;
        incorrectCount = incorrect;
        var scoreEl  = document.getElementById('correct-count');
        var wrongEl  = document.getElementById('incorrect-count');
        if (scoreEl) scoreEl.textContent = correct;
        if (wrongEl) wrongEl.textContent = incorrect;

        showQuizSummary(totalQ, attempted, unattempted, correct, incorrect, autoExpired);

        var quizBar = document.getElementById('quiz-bottom-bar');
        if (quizBar) quizBar.style.display = 'none';
    });
}

function showQuizSummary(total, attempted, unattempted, correct, incorrect, timedOut) {
    const overlay = document.getElementById('quiz-summary-overlay');
    if (!overlay) return;

    const safe = function (id, val) { const el = document.getElementById(id); if (el) el.textContent = val; };
    safe('qs-total',       total);
    safe('qs-attempted',   attempted);
    safe('qs-unattempted', unattempted);
    safe('qs-correct',     correct);
    safe('qs-incorrect',   incorrect);

    const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
    safe('qs-percent', pct + '%');

    const titleEl    = document.getElementById('qs-title');
    const subtitleEl = document.getElementById('qs-subtitle');
    if (titleEl)    titleEl.textContent    = timedOut ? "Time's Up!"         : 'Quiz Submitted!';
    if (subtitleEl) subtitleEl.textContent = timedOut ? 'Timer ended - here are your results.' : 'Your quiz has been submitted.';

    overlay.classList.add('open');
    document.body.classList.remove('quiz-mode-active');
}

function closeQuizSummary() {
    const overlay = document.getElementById('quiz-summary-overlay');
    if (overlay) overlay.classList.remove('open');
    const paginationWrap = document.getElementById('pagination-wrap');
    if (paginationWrap) paginationWrap.style.display = '';
    const allCards = document.querySelectorAll('.question-card');
    totalPages = Math.ceil(allCards.length / QUESTIONS_PER_PAGE);
    goToPage(1);
}

function openReportModal(qId) {
    window.currentReportQId = qId;
    const modal     = document.getElementById('report-issue-modal');
    const modalBody = document.getElementById('report-modal-body');
    const successMsg = document.getElementById('report-success-message');
    const textarea  = document.getElementById('report-problem-textarea');
    const feedback  = document.getElementById('report-modal-feedback');
    const submitBtn = document.getElementById('submit-report-btn');
    if (!modal) return;
    if (modalBody)   modalBody.style.display  = '';
    if (successMsg)  successMsg.style.display = 'none';
    if (textarea)    textarea.value = '';
    if (feedback)    { feedback.textContent = ''; feedback.className = ''; }
    if (submitBtn)   { submitBtn.disabled = false; submitBtn.innerHTML = 'Submit Report'; }
    modal.classList.add('open');
    if (textarea) setTimeout(function () { textarea.focus(); }, 100);
}

function closeReportModal() {
    const modal     = document.getElementById('report-issue-modal');
    const modalBody = document.getElementById('report-modal-body');
    const successMsg = document.getElementById('report-success-message');
    const textarea  = document.getElementById('report-problem-textarea');
    const feedback  = document.getElementById('report-modal-feedback');
    const submitBtn = document.getElementById('submit-report-btn');
    if (!modal) return;
    modal.classList.remove('open');
    if (textarea)    textarea.value = '';
    if (successMsg)  successMsg.style.display = 'none';
    if (modalBody)   modalBody.style.display  = '';
    if (feedback)    { feedback.textContent = ''; feedback.className = ''; }
    if (submitBtn)   { submitBtn.disabled = false; submitBtn.innerHTML = 'Submit Report'; }
    window.currentReportQId = null;
}

function setModalFeedback(message, type) {
    const feedback = document.getElementById('report-modal-feedback');
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className   = 'modal-feedback-msg ' + (type || '');
}

function submitReport(event) {
    event.preventDefault();
    const textarea  = document.getElementById('report-problem-textarea');
    const submitBtn = document.getElementById('submit-report-btn');
    const problem   = textarea ? textarea.value.trim() : '';

    if (problem.length < 10) {
        setModalFeedback('Please describe the issue in at least 10 characters.', 'error');
        if (textarea) textarea.focus();
        return;
    }
    if (!window.currentReportQId) {
        setModalFeedback('Unable to identify the question. Please try again.', 'error');
        return;
    }
    if (submitBtn) {
        submitBtn.disabled  = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Submitting...';
    }

    fetch('/report_issue/' + window.currentReportQId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem: problem })
    })
    .then(function (response) {
        if (!response.ok) throw new Error('Server error ' + response.status);
        return response.json();
    })
    .then(function (data) {
        if (data.message) {
            const modalBody  = document.getElementById('report-modal-body');
            const successMsg = document.getElementById('report-success-message');
            if (modalBody)  modalBody.style.display  = 'none';
            if (successMsg) successMsg.style.display = 'block';
            setTimeout(closeReportModal, 2000);
        } else {
            setModalFeedback(data.error || 'Submission failed. Please try again.', 'error');
            if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = 'Submit Report'; }
        }
    })
    .catch(function () {
        setModalFeedback('Network error. Please try again.', 'error');
        if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = 'Submit Report'; }
    });
}

function goToPage(page) {
    const allCards = document.querySelectorAll('.question-card');
    if (!allCards.length) return;

    totalPages = Math.ceil(allCards.length / QUESTIONS_PER_PAGE);
    page       = Math.max(1, Math.min(page, totalPages));
    currentPage = page;

    const start = (page - 1) * QUESTIONS_PER_PAGE;
    const end   = start + QUESTIONS_PER_PAGE;

    allCards.forEach(function (card, index) {
        card.style.display = (index >= start && index < end) ? '' : 'none';
    });

    renderPagination(totalPages, currentPage);

    const topbar = document.querySelector('.quiz-topbar');
    if (topbar) {
        const offset = topbar.getBoundingClientRect().top + window.scrollY - 16;
        window.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' });
    } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function renderPagination(total, current) {
    const wrap = document.getElementById('pagination-wrap');
    if (!wrap) return;
    if (total <= 1) { wrap.innerHTML = ''; return; }

    let html = '';
    html += '<button class="pg-btn pg-prev" onclick="goToPage(' + (current - 1) + ')"' +
        (current === 1 ? ' disabled' : '') +
        ' aria-label="Previous page"><i class="fas fa-chevron-left" aria-hidden="true"></i></button>';

    const delta = 2;
    const pages = [];
    for (let i = 1; i <= total; i++) {
        if (i === 1 || i === total || (i >= current - delta && i <= current + delta)) {
            pages.push(i);
        }
    }

    let prev = null;
    for (const p of pages) {
        if (prev !== null && p - prev > 1) html += '<span class="pg-ellipsis">&hellip;</span>';
        const isActive = p === current;
        html += '<button class="pg-btn' + (isActive ? ' active' : '') + '" onclick="goToPage(' + p + ')"' +
            ' aria-label="Page ' + p + '"' + (isActive ? ' aria-current="page"' : '') + '>' + p + '</button>';
        prev = p;
    }

    html += '<button class="pg-btn pg-next" onclick="goToPage(' + (current + 1) + ')"' +
        (current === total ? ' disabled' : '') +
        ' aria-label="Next page"><i class="fas fa-chevron-right" aria-hidden="true"></i></button>';

    wrap.innerHTML = html;
}

function validateTimerInput() {
    const input   = document.getElementById('popup-timer-input');
    const errorEl = document.getElementById('popup-timer-error');
    if (!input || input.value.trim() === '') {
        if (errorEl) errorEl.textContent = '';
        return true;
    }
    const val = parseInt(input.value, 10);
    if (isNaN(val) || val < 1 || val > 300) {
        if (errorEl) errorEl.textContent = 'Enter a value between 1 and 300 minutes.';
        if (input)   input.focus();
        return false;
    }
    if (errorEl) errorEl.textContent = '';
    return true;
}

function getPopupTimerMinutes() {
    const input = document.getElementById('popup-timer-input');
    if (!input || input.value.trim() === '') return 0;
    return parseInt(input.value.trim(), 10) || 0;
}

function startPractice() {
    if (!validateTimerInput()) return;
    const minutes = getPopupTimerMinutes();
    closePreSessionPopup();
    isQuizMode    = false;
    quizSubmitted = false;

    if (minutes > 0) {
        const s = loadSession();
        s.timerEnabled     = true;
        s.timerSecondsLeft = minutes * 60;
        s.timerSavedAt     = Date.now();
        saveSession(s);
        startGlobalTimer(minutes * 60);
    }

    const allCards = document.querySelectorAll('.question-card');
    totalPages = Math.ceil(allCards.length / QUESTIONS_PER_PAGE);
    goToPage(1);
}

function startQuiz() {
    if (!validateTimerInput()) return;
    const minutes = getPopupTimerMinutes();
    closePreSessionPopup();
    isQuizMode    = true;
    quizSubmitted = false;

    document.body.classList.add('quiz-mode-active');


    const paginationWrap = document.getElementById('pagination-wrap');
    if (paginationWrap) paginationWrap.style.display = 'none';


    const quizBar = document.getElementById('quiz-bottom-bar');
    if (quizBar) quizBar.style.display = 'flex';


    document.querySelectorAll('.question-card').forEach(function (card) {
        card.style.display = '';
        const qId      = card.id.replace('question-', '');
        const submitBtn = document.getElementById('submit-' + qId);
        if (submitBtn) submitBtn.style.display = 'none';
    });

    if (minutes > 0) {
        const s = loadSession();
        s.timerEnabled     = true;
        s.timerSecondsLeft = minutes * 60;
        s.timerSavedAt     = Date.now();
        saveSession(s);
        startGlobalTimer(minutes * 60);
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closePreSessionPopup() {
    const popup = document.getElementById('pre-session-popup');
    if (popup) popup.classList.remove('open');
}

function openPreSessionPopup() {
    const popup = document.getElementById('pre-session-popup');
    if (popup) popup.classList.add('open');
}

function restoreSelectedOptions(selectedOptions) {
    if (!selectedOptions) return;
    Object.entries(selectedOptions).forEach(function (entry) {
        const qId   = entry[0];
        const value = entry[1];
        if (!value)                        return;
        if (answeredQuestions.has(qId))    return;

        userSelectedOptions[qId] = value;

        const card = document.getElementById('question-' + qId);
        if (!card) return;
        const qType = getQuestionType(card);

        if (qType === 'NAT') {
            const input = document.getElementById('nat-' + qId);
            if (input) input.value = value;

        } else if (qType === 'MSQ') {
            const vals = Array.isArray(value) ? value : [value];
            const form = document.getElementById('form-' + qId);
            if (form) {
                vals.forEach(function (v) {
                    const cb = form.querySelector('input[type="checkbox"][value="' + CSS.escape(v) + '"]');
                    if (cb) {
                        cb.checked = true;
                        const row = cb.closest('.option-row');
                        if (row) row.classList.add('selected');
                    }
                });
            }
        } else {
            const form = document.getElementById('form-' + qId);
            if (form) {
                const radio = form.querySelector('input[type="radio"][value="' + CSS.escape(value) + '"]');
                if (radio) {
                    radio.checked = true;
                    const row = radio.closest('.option-row');
                    if (row) row.classList.add('selected');
                }
            }
        }
    });
}

function initPreSessionPopup() {
    const s            = loadSession();
    const hasAnswered  = Object.keys(s.answered).length > 0;

    if (hasAnswered) {
        correctCount   = s.scores.correct   || 0;
        incorrectCount = s.scores.incorrect || 0;

        const correctEl   = document.getElementById('correct-count');
        const incorrectEl = document.getElementById('incorrect-count');
        if (correctEl)   correctEl.textContent   = correctCount;
        if (incorrectEl) incorrectEl.textContent  = incorrectCount;


        if (s.isQuizMode)    isQuizMode    = true;
        if (s.quizSubmitted) quizSubmitted = true;


        Object.entries(s.answered).forEach(function (entry) {
            const qId  = entry[0];
            const data = entry[1];
            const card = document.getElementById('question-' + qId);
            if (!card) return;

            answeredQuestions.add(qId);
            storedExplanations[qId] = data.answer_text || 'No explanation available.';


            if (data.user_selected !== undefined && data.user_selected !== null) {
                userSelectedOptions[qId] = data.user_selected;
            }

            const form  = document.getElementById('form-' + qId);
            const qType = getQuestionType(card);

            lockQuestion(qId, qType, form);
            const submitBtn = document.getElementById('submit-' + qId);
            if (submitBtn) submitBtn.style.display = 'none';

            showResultFromCache(qId, data);
            markQuestionStatus(qId, data.is_correct ? 'correct' : 'incorrect');
        });

        restoreSelectedOptions(s.selectedOptions || {});


        if (s.timerEnabled && s.timerSecondsLeft > 0) {
            const elapsed   = s.timerSavedAt ? Math.round((Date.now() - s.timerSavedAt) / 1000) : 0;
            const remaining = s.timerSecondsLeft - elapsed;
            if (remaining > 0) {
                startGlobalTimer(remaining);
            } else {
                onGlobalTimerExpired();
            }
        }

        const allCards = document.querySelectorAll('.question-card');
        totalPages     = Math.ceil(allCards.length / QUESTIONS_PER_PAGE);
        goToPage(1);


        const allAnswered = Array.from(allCards).every(function (c) {
            return answeredQuestions.has(c.id.replace('question-', ''));
        });
        if (allAnswered && !timerExpired && !isQuizMode) {
            stopGlobalTimer();
            showSessionCompletePopup();
        }
        return;
    }

    openPreSessionPopup();


    const timerInput = document.getElementById('popup-timer-input');
    if (timerInput) {
        timerInput.addEventListener('input', function () {
            const errorEl = document.getElementById('popup-timer-error');
            if (errorEl) errorEl.textContent = '';
        });
        timerInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); startPractice(); }
        });
    }
}

function initOptionRows() {
    document.querySelectorAll('.option-row').forEach(function (row) {
        row.addEventListener('click', function (e) {
            if (e.target.tagName === 'INPUT') return;
            const inp = this.querySelector('input');
            if (!inp || inp.disabled) return;

            const card = this.closest('.question-card');
            if (!card) return;
            if (card.classList.contains('answered-correct')       ||
                card.classList.contains('answered-incorrect')      ||
                card.classList.contains('answered-not-attempted')) return;
            if (timerExpired) return;

            const qId = card.id.replace('question-', '');
            if (answeredQuestions.has(qId)) return;

            if (inp.type === 'radio') {

                document.querySelectorAll('input[name="' + inp.name + '"]').forEach(function (r) {
                    const rRow = r.closest('.option-row');
                    if (rRow) rRow.classList.remove('selected');
                });
                inp.checked = true;
                this.classList.add('selected');
                persistSelectedOption(qId, inp.value);

            } else if (inp.type === 'checkbox') {
                inp.checked = !inp.checked;
                this.classList.toggle('selected', inp.checked);
                const form = card.querySelector('form');
                if (form) {
                    const checked = Array.from(form.querySelectorAll('input[type="checkbox"]:checked'))
                        .map(function (cb) { return cb.value; });
                    persistSelectedOption(qId, checked.length ? checked : null);
                }
            }
        });
    });

    document.querySelectorAll('.nat-input').forEach(function (input) {
        input.addEventListener('change', function () {
            if (timerExpired) return;
            const qId = this.id.replace('nat-', '');
            if (this.value.trim()) persistSelectedOption(qId, this.value.trim());
        });
    });
}

function initNatInputs() {
    document.querySelectorAll('.nat-input').forEach(function (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (timerExpired || isQuizMode) return;
                const form = this.closest('form');
                if (form) form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
            }
        });
        input.addEventListener('input', function () {
            const qId = this.id.replace('nat-', '');
            const existing = document.getElementById('inline-error-' + qId);
            if (existing) existing.remove();
        });
    });
}

function initModalOverlayClose() {
    const modal = document.getElementById('report-issue-modal');
    if (!modal) return;
    modal.addEventListener('click', function (e) {
        if (e.target === this) closeReportModal();
    });
}

function initKeyboardClose() {
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('report-issue-modal');
            if (modal && modal.classList.contains('open')) closeReportModal();
        }
    });
}

document.addEventListener('DOMContentLoaded', function () {
    initOptionRows();
    initModalOverlayClose();
    initKeyboardClose();
    initNatInputs();
    initPreSessionPopup();
});