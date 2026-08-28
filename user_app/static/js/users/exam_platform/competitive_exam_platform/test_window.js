const testManager = {
    questions: [],
    userAnswers: [],
    currentQuestionIndex: -1,
    currentSectionId: null,
    timeLeft: initialDurationSeconds,
    timerInterval: null,
    questionIdToIndexMap: new Map(),
    init: async function(testKey, courseCode, uniqueCode) {
        await this.fetchAllQuestions(testKey, courseCode, uniqueCode);
        const numQuestions = this.questions.length;
        this.userAnswers = new Array(numQuestions).fill(null);
        this.questions.forEach((q, index) => {
            this.userAnswers[index] = {
                questionDbId: q.id,
                overallQuestionIndex: index,
                sectionId: q.section_id,
                status: 'not_visited',
                selectedOption: null,
                writtenAnswer: '',
                timeSpentOnQuestion: 0
            };
            this.questionIdToIndexMap.set(q.id, index);
        });
        document.getElementById('not-visited-count').textContent = numQuestions;
        document.getElementById('not-answered-count').textContent = 0;
        document.getElementById('answered-count').textContent = 0;
        document.getElementById('marked-review-count').textContent = 0;
        document.getElementById('answered-marked-count').textContent = 0;
        this.buildQuestionPalette();
        this.attachEventListeners();

        if (window.innerWidth > 992) {
            document.querySelector('.content').classList.remove('right-panel-hidden');
        }

        if (numQuestions > 0) {
            if (typeof sectionsData !== 'undefined' && sectionsData.length > 0) {
                this.selectSection(sectionsData[0].section_id);
            } else {
                this.currentSectionId = this.questions[0].section_id;
                this.loadQuestionByIndex(0);
            }
        } else {
            document.getElementById('question-box-container').innerHTML = "<p>No questions available for this test.</p>";
        }
        this.startTimer();
    },

    fetchAllQuestions: async function(testKey, courseCode, uniqueCode) {
        try {
            const response = await fetch(`/fetch-questions/${sectionId}/${testKey}/${courseCode}/${uniqueCode}`);
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`HTTP error! status: ${response.status} - ${errText}`);
            }
            this.questions = await response.json();
        } catch (error) {
            console.error("Failed to fetch questions:", error);
            sppExamToast("Failed to load questions. Please refresh the page.");
        }
    },

    buildQuestionPalette: function() {
        const paletteContainer = document.getElementById('question-palette-container');
        paletteContainer.innerHTML = '';
        const fragment = document.createDocumentFragment();
        sectionsData.forEach(section => {
            const sectionId = String(section.section_id);
            const sectionBox = document.createElement('div');
            sectionBox.className = 'section-box';
            sectionBox.id = `section-palette-${sectionId}`;
            if (this.currentSectionId && this.currentSectionId !== sectionId) {
                sectionBox.style.display = 'none';
            }
            const sectionTitle = document.createElement('div');
            sectionTitle.className = 'section-title';
            sectionTitle.textContent = section.section_name;
            sectionBox.appendChild(sectionTitle);
            const chooseLabel = document.createElement('div');
            chooseLabel.className = 'choose-label';
            chooseLabel.textContent = 'Choose a Question';
            sectionBox.appendChild(chooseLabel);
            const grid = document.createElement('div');
            grid.className = 'question-grid';
            this.questions.filter(q => String(q.section_id) === sectionId).forEach(q => {
                const btn = document.createElement('button');
                btn.className = 'qbtn gray-box';
                btn.textContent = q.question_number_in_section;
                btn.id = `qbtn_${q.id}`;
                btn.type = 'button';
                btn.onclick = () => {
                    this.loadQuestionByIndex(this.questionIdToIndexMap.get(q.id));
                    if (window.innerWidth <= 992) {
                        document.querySelector('.content').classList.add('right-panel-hidden');
                    }
                };
                grid.appendChild(btn);
            });
            sectionBox.appendChild(grid);
            fragment.appendChild(sectionBox);
        });
        paletteContainer.appendChild(fragment);
    },

    updateQuestionPaletteButton: function(questionDbId, newStatus) {
        const btn = document.getElementById(`qbtn_${questionDbId}`);
        if (!btn) return;
        let newClassName = 'qbtn ';
        const buttonNumberText = btn.textContent.match(/\d+/) ? btn.textContent.match(/\d+/)[0] : btn.textContent;
        btn.innerHTML = '';
        switch(newStatus) {
            case 'answered':
                newClassName += 'shield green-shield';
                btn.textContent = buttonNumberText;
                break;
            case 'not_answered':
                newClassName += 'shield red-shield';
                btn.textContent = buttonNumberText;
                break;
            case 'marked_review':
                newClassName += 'circle purple-circle';
                btn.textContent = buttonNumberText;
                break;
            case 'answered_marked_review':
                newClassName += 'purple-green-circle';
                const iconSpan = document.createElement('span');
                iconSpan.className = 'center-icon';
                iconSpan.textContent = '✓';
                btn.appendChild(iconSpan);
                btn.appendChild(document.createTextNode(` ${buttonNumberText}`));
                break;
            case 'not_visited':
            default:
                newClassName += 'box gray-box';
                btn.textContent = buttonNumberText;
        }
        btn.className = newClassName;
    },

    updateStatusCounts: function() {
        const counts = { answered: 0, not_answered: 0, not_visited: 0, marked_review: 0, answered_marked_review: 0 };
        this.userAnswers.forEach(ua => {
            if (ua && counts[ua.status] !== undefined) {
                counts[ua.status]++;
            }
        });
        document.getElementById('answered-count').textContent = counts.answered + counts.answered_marked_review;
        document.getElementById('not-answered-count').textContent = counts.not_answered;
        document.getElementById('not-visited-count').textContent = counts.not_visited;
        document.getElementById('marked-review-count').textContent = counts.marked_review + counts.answered_marked_review;
        document.getElementById('answered-marked-count').textContent = counts.answered_marked_review;
    },
    loadQuestionByIndex: function(index) {
        if (index < 0 || index >= this.questions.length) {
            return;
        }
        this.currentQuestionIndex = index;
        const question = this.questions[this.currentQuestionIndex];
        const userAnswer = this.userAnswers[this.currentQuestionIndex];
        if (userAnswer.status === 'not_visited') {
            userAnswer.status = 'not_answered';
            this.updateQuestionPaletteButton(question.id, 'not_answered');
            this.updateStatusCounts();
        }
        if (this.currentSectionId !== question.section_id) {
            this.currentSectionId = question.section_id;
            this.updateSectionTabActive();
            this.showPaletteForSection(this.currentSectionId);
        }
        this._renderQuestion(question);
        this.highlightCurrentQuestionInPalette();
    },

    _renderQuestion: function(question) {
        const questionBox = document.getElementById('question-box-container');
        document.getElementById('question-type-display').textContent = question.question_type;
        document.getElementById('correct-marks-display').textContent = question.correct_marks;
        document.getElementById('negative-marks-display').textContent = question.negative_marks || '0';
        document.getElementById('question-number-display').textContent = `Question No. ${question.question_number_in_section}`;

        const questionTextArea = document.getElementById('question-text-area');
        questionTextArea.innerHTML = question.question_text || '';

        const optionsArea = document.getElementById('question-options-area');
        optionsArea.innerHTML = '';
        const userAnswer = this.userAnswers[this.currentQuestionIndex];
        const fragment = document.createDocumentFragment();

        const imageRegions = question.option_regions || {};
        const isImageQuestion = question.question_image && Object.keys(imageRegions).length > 0 &&
            (question.question_type === 'MCQ' || question.question_type === 'MSQ');

        if (isImageQuestion) {
            const isMSQ = question.question_type === 'MSQ';
            const wrap = document.createElement('div');
            wrap.className = 'qimg-wrap';
            const inner = document.createElement('div');
            inner.className = 'qimg-inner';
            const qImg = document.createElement('img');
            qImg.src = question.question_image.charAt(0) === '/' ? question.question_image : '/' + question.question_image;
            qImg.alt = 'Question image';
            qImg.draggable = false;
            inner.appendChild(qImg);
            wrap.appendChild(inner);

            Object.keys(imageRegions).forEach(optKey => {
                const box = imageRegions[optKey];
                if (!box) return;

                const input = document.createElement('input');
                input.type = isMSQ ? 'checkbox' : 'radio';
                input.name = `q_${question.id}_option`;
                input.value = optKey;
                input.hidden = true;
                input.dataset.questionDbId = question.id;

                const picked = userAnswer.selectedOption;
                const isSelected = isMSQ
                    ? (Array.isArray(picked) && picked.includes(optKey))
                    : picked === optKey;
                if (isSelected) input.checked = true;

                const hot = document.createElement('div');
                hot.className = 'qimg-hot';
                hot.style.left = box.x + '%';
                hot.style.top = box.y + '%';
                hot.style.width = box.w + '%';
                hot.style.height = box.h + '%';

                const dot = document.createElement('div');
                dot.className = 'qimg-dot' + (isSelected ? ' is-picked' : '');
                dot.style.top = (box.y + box.h / 2) + '%';
                dot.setAttribute('role', isMSQ ? 'checkbox' : 'radio');
                dot.setAttribute('aria-label', 'Option ' + optKey.toUpperCase());
                dot.tabIndex = 0;

                const choose = () => {
                    if (isMSQ) {
                        input.checked = !input.checked;
                        dot.classList.toggle('is-picked', input.checked);
                    } else {
                        optionsArea.querySelectorAll(`input[name="q_${question.id}_option"]`).forEach(i => { i.checked = false; });
                        inner.querySelectorAll('.qimg-dot').forEach(n => n.classList.remove('is-picked'));
                        input.checked = true;
                        dot.classList.add('is-picked');
                    }
                };
                hot.addEventListener('click', choose);
                dot.addEventListener('click', choose);
                dot.addEventListener('keydown', ev => {
                    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choose(); }
                });

                fragment.appendChild(input);
                inner.appendChild(hot);
                inner.appendChild(dot);
            });
            fragment.appendChild(wrap);
        } else if (question.question_type === 'MCQ' || question.question_type === 'MSQ') {
            const optionType = question.question_type === 'MCQ' ? 'radio' : 'checkbox';
            ['a', 'b', 'c', 'd'].forEach(optKey => {
                if (question.options && question.options[optKey]) {
                    const label = document.createElement('label');
                    label.className = 'option-label';

                    const input = document.createElement('input');
                    input.type = optionType;
                    input.name = `q_${question.id}_option`;
                    input.value = optKey;
                    input.dataset.questionDbId = question.id;

                    if (question.question_type === 'MCQ' && userAnswer.selectedOption === optKey) {
                        input.checked = true;
                    } else if (question.question_type === 'MSQ' && Array.isArray(userAnswer.selectedOption) && userAnswer.selectedOption.includes(optKey)) {
                        input.checked = true;
                    }

                    const optionContent = document.createElement('span');
                    optionContent.className = 'option-content';
                    optionContent.innerHTML = ` ${question.options[optKey]}`;

                    label.appendChild(input);
                    label.appendChild(optionContent);
                    fragment.appendChild(label);
                }
            });
        }else if (question.question_type === 'NAT') {
        const natContainer = document.createElement('div');
        natContainer.className = 'nat-keypad-container';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'nat-input';
        input.placeholder = 'Enter your answer here';
        input.dataset.questionDbId = question.id;
        input.value = userAnswer.writtenAnswer || '';

        input.addEventListener('keydown', (e) => {
            if (['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab', 'Home', 'End'].includes(e.key)) {
                return;
            }
            if (e.key === '-' && e.target.selectionStart === 0 && !e.target.value.includes('-')) {
                return;
            }
            if (e.key === '.' && !e.target.value.includes('.')) {
                return;
            }
            if (/\d/.test(e.key)) {
                return;
            }
            e.preventDefault();
        });

        natContainer.appendChild(input);

        const keypad = document.createElement('div');
        keypad.className = 'keypad';

        const buttonsLayout = [
            ['Backspace'],
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['0', '.', '-'],
            ['\u2190', '\u2192'],
            ['Clear All']
        ];

        buttonsLayout.forEach(row => {
            const rowDiv = document.createElement('div');
            rowDiv.className = 'keypad-row';
            row.forEach(key => {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = key;
                button.className = 'keypad-btn';
                if (key === 'Backspace' || key === 'Clear All') {
                    button.classList.add('keypad-btn-wide');
                }

                button.addEventListener('click', () => {
                    const start = input.selectionStart;
                    const end = input.selectionEnd;
                    const currentValue = input.value;
                    input.focus();

                    switch (key) {
                        case 'Backspace':
                            if (start > 0) {
                                input.value = currentValue.substring(0, start - 1) + currentValue.substring(end);
                                input.setSelectionRange(start - 1, start - 1);
                            }
                            break;
                        case 'Clear All':
                            input.value = '';
                            break;
                        case '\u2190':
                            if (start > 0) {
                                input.setSelectionRange(start - 1, start - 1);
                            }
                            break;
                        case '\u2192':
                            if (start < currentValue.length) {
                                input.setSelectionRange(start + 1, start + 1);
                            }
                            break;
                        case '.':
                            if (!currentValue.includes('.')) {
                                input.value = currentValue.slice(0, start) + key + currentValue.slice(end);
                                input.setSelectionRange(start + 1, start + 1);
                            }
                            break;
                        case '-':
                            if (start === 0 && !currentValue.includes('-')) {
                                input.value = key + currentValue;
                                input.setSelectionRange(start + 1, start + 1);
                            }
                            break;
                        default:
                            input.value = currentValue.slice(0, start) + key + currentValue.slice(end);
                            input.setSelectionRange(start + 1, start + 1);
                            break;
                    }
                });
                rowDiv.appendChild(button);
            });
            keypad.appendChild(rowDiv);
        });

        natContainer.appendChild(keypad);
        fragment.appendChild(natContainer);
    }
    optionsArea.appendChild(fragment);
    this._enhanceContent(questionTextArea);
    this._enhanceContent(optionsArea);
   },

    _enhanceContent: function(container) {
        if (!container) return;
        try {
            if (typeof renderMathInElement === 'function') {
                renderMathInElement(container, {
                    delimiters: [
                        { left: '$$', right: '$$', display: true },
                        { left: '$', right: '$', display: false }
                    ],
                    throwOnError: false
                });
            }
        } catch (e) {
            console.warn('TEST WINDOW: math render skipped:', e);
        }
        try {
            if (window.hljs) {
                container.querySelectorAll('pre').forEach(function(block) {
                    if (!block.dataset.highlighted) {
                        hljs.highlightElement(block);
                        block.dataset.highlighted = 'yes';
                    }
                });
            }
        } catch (e) {
            console.warn('TEST WINDOW: code highlight skipped:', e);
        }
    },

    lastHighlightedButtonId: null,
    highlightCurrentQuestionInPalette: function() {
        if (this.lastHighlightedButtonId) {
            const prevBtn = document.getElementById(this.lastHighlightedButtonId);
            if (prevBtn) prevBtn.style.border = "1px solid #999";
        }
        if (this.currentQuestionIndex !== -1) {
            const currentQuestion = this.questions[this.currentQuestionIndex];
            const currentBtnId = `qbtn_${currentQuestion.id}`;
            const currentBtn = document.getElementById(currentBtnId);
            if (currentBtn) {
                currentBtn.style.border = "2px solid #007bff";
                this.lastHighlightedButtonId = currentBtnId;
                currentBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    },

    selectSection: function(sectionId) {
        this.currentSectionId = sectionId;
        this.updateSectionTabActive();
        this.showPaletteForSection(sectionId);
        const firstQuestionOfSectionIndex = this.questions.findIndex(q => String(q.section_id) === String(sectionId));
        if (firstQuestionOfSectionIndex !== -1) {
            this.loadQuestionByIndex(firstQuestionOfSectionIndex);
        } else {
            document.getElementById('question-box-container').innerHTML = `<p>No questions available in this section.</p>`;
            this.currentQuestionIndex = -1;
            this.highlightCurrentQuestionInPalette();
        }
    },

    updateSectionTabActive: function() {
        document.querySelectorAll('#section-tabs-container .tab').forEach(tab => {
            tab.classList.toggle('active-tab', String(tab.dataset.sectionId) === String(this.currentSectionId));
            tab.classList.toggle('inactive-tab', String(tab.dataset.sectionId) !== String(this.currentSectionId));
        });
    },

    showPaletteForSection: function(sectionId) {
        document.querySelectorAll('.section-box').forEach(box => {
            box.style.display = box.id === `section-palette-${sectionId}` ? 'block' : 'none';
        });
    },

    _handleSave: function(isMarkForReview = false) {
        if (this.currentQuestionIndex === -1) return;
        const question = this.questions[this.currentQuestionIndex];
        const userAnswer = this.userAnswers[this.currentQuestionIndex];
        const optionsArea = document.getElementById('question-options-area');
        let answered = false;

        if (question.question_type === 'MCQ') {
            const selectedRadio = optionsArea.querySelector(`input[name="q_${question.id}_option"]:checked`);
            userAnswer.selectedOption = selectedRadio ? selectedRadio.value : null;
            answered = !!selectedRadio;
        } else if (question.question_type === 'MSQ') {
            const selectedCheckboxes = Array.from(optionsArea.querySelectorAll(`input[name="q_${question.id}_option"]:checked`));
            userAnswer.selectedOption = selectedCheckboxes.length > 0 ? selectedCheckboxes.map(cb => cb.value) : [];
            answered = selectedCheckboxes.length > 0;
        } else if (question.question_type === 'NAT') {
            const natInput = optionsArea.querySelector(`.nat-input[data-question-db-id="${question.id}"]`);
            userAnswer.writtenAnswer = natInput ? natInput.value.trim() : '';
            answered = userAnswer.writtenAnswer !== '';
        }

        userAnswer.status = isMarkForReview ? (answered ? 'answered_marked_review' : 'marked_review') : (answered ? 'answered' : 'not_answered');

        this.updateQuestionPaletteButton(question.id, userAnswer.status);
        this.updateStatusCounts();

        if (this.currentQuestionIndex < this.questions.length - 1) {
            this.loadQuestionByIndex(this.currentQuestionIndex + 1);
        } else {
            sppExamConfirm("You are at the last question. Go back to the first question?",
                () => this.loadQuestionByIndex(0));
        }
    },

    clearResponse: function() {
        if (this.currentQuestionIndex === -1) return;
        const question = this.questions[this.currentQuestionIndex];
        const userAnswer = this.userAnswers[this.currentQuestionIndex];
        const optionsArea = document.getElementById('question-options-area');
        if (question.question_type === 'MCQ' || question.question_type === 'MSQ') {
            optionsArea.querySelectorAll(`input[name="q_${question.id}_option"]:checked`).forEach(input => input.checked = false);
            userAnswer.selectedOption = question.question_type === 'MSQ' ? [] : null;
        } else if (question.question_type === 'NAT') {
            const natInput = optionsArea.querySelector(`.nat-input[data-question-db-id="${question.id}"]`);
            if (natInput) natInput.value = '';
            userAnswer.writtenAnswer = '';
        }
        userAnswer.status = userAnswer.status === 'answered_marked_review' ? 'marked_review' : 'not_answered';
        this.updateQuestionPaletteButton(question.id, userAnswer.status);
        this.updateStatusCounts();
    },

    startTimer: function() {
        const timerDisplay = document.getElementById('time-left-display');
        if (!timerDisplay) return;
        // A missing / zero / non-numeric duration must never be read as
        // "0 seconds left" and auto-submit an untouched test on the first tick.
        // Only a real positive countdown is allowed to end the test.
        const secs = Number(this.timeLeft);
        if (!isFinite(secs) || secs <= 0) {
            timerDisplay.textContent = "Time Left : --:--";
            return;
        }
        this.timeLeft = Math.floor(secs);
        this.timerInterval = setInterval(() => {
            this.timeLeft--;
            const minutes = Math.floor(this.timeLeft / 60);
            const seconds = this.timeLeft % 60;
            timerDisplay.textContent = `Time Left : ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            if (this.timeLeft <= 0) {
                clearInterval(this.timerInterval);
                timerDisplay.textContent = "Time Up! Submitting Test...";
                sppExamToast("Time is up. Submitting your test automatically...");
                this.submitTest(true);
            }
        }, 1000);
    },

    submitTest: async function(isAutoSubmit = false) {
        clearInterval(this.timerInterval);
        window.sppAllowFsExit = true;
        document.querySelectorAll('button, input').forEach(el => el.disabled = true);

        const submissionData = {
            test_key: testKey,
            answers: this.userAnswers.map(ua => ({
                question_id: ua.questionDbId,
                status_from_client: ua.status,
                selected_option: ua.selectedOption,
                written_answer: ua.writtenAnswer,
                time_spent_on_question: ua.timeSpentOnQuestion || 0
            })),
            total_time_taken: initialDurationSeconds - Math.max(0, this.timeLeft),
            device_info: navigator.userAgent
        };

        try {
           const response = await fetch(`/submit-test-action/${sectionId}/${testKey}/${courseCode}/${uniqueCode}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(submissionData)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status} - ${errorText}`);
            }

           const result = await response.json();
            if (result.redirect_url) {
                if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
                window.location.replace(result.redirect_url);
            } else {
                sppExamToast("Test submitted successfully!");
            }
        } catch (error) {
            window.sppAllowFsExit = false;
            sppExamToast(`Test submission failed: ${error.message}. Please contact support.`);
            document.querySelectorAll('button, input').forEach(el => el.disabled = false);
        }
    },

    attachEventListeners: function() {
        const saveNextBtn = document.getElementById('save-next-btn');
        const markReviewBtn = document.getElementById('mark-review-next-btn');
        const clearBtn = document.getElementById('clear-response-btn');
        const submitBtn = document.getElementById('submit-test-btn');
        if (saveNextBtn) saveNextBtn.onclick = () => this._handleSave(false);
        if (markReviewBtn) markReviewBtn.onclick = () => this._handleSave(true);
        if (clearBtn) clearBtn.onclick = () => this.clearResponse();
        if (submitBtn) submitBtn.onclick = () => {
            sppExamConfirm("Are you sure you want to submit the test?", () => this.submitTest());
        };

        const paletteToggleBtn = document.getElementById('palette-toggle-btn');
        const closePaletteBtn = document.getElementById('close-palette-btn');
        const contentDiv = document.querySelector('.content');
        const backdrop = document.querySelector('.sidebar-backdrop');
        const togglePalette = () => {
            if (contentDiv) contentDiv.classList.toggle('right-panel-hidden');
        };
        if (paletteToggleBtn) paletteToggleBtn.onclick = togglePalette;
        if (backdrop) backdrop.onclick = togglePalette;
        if (closePaletteBtn) closePaletteBtn.onclick = togglePalette;

        const instructionsModal = document.getElementById("instructions-modal");
        const viewInstructionsBtn = document.getElementById("view-instructions-btn");
        const closeInstructionsBtn = document.getElementById("close-instructions-btn");
        if (viewInstructionsBtn && instructionsModal) viewInstructionsBtn.onclick = () => { instructionsModal.style.display = "block"; };
        if (closeInstructionsBtn && instructionsModal) closeInstructionsBtn.onclick = () => { instructionsModal.style.display = "none"; };

        const calculatorPopup = document.getElementById("calculator-popup");
        const calculatorIcon = document.querySelector(".calculator-icon");
        const closeCalculatorBtn = document.getElementById("close-calculator-btn");
        const helpBtn = document.getElementById("calculator-help-btn");
        const helpContent = document.getElementById("helpContent");

        if (calculatorIcon && calculatorPopup) {
            calculatorIcon.onclick = () => { calculatorPopup.style.display = "block"; };
        }
        if (closeCalculatorBtn && calculatorPopup) {
            closeCalculatorBtn.onclick = () => {
                calculatorPopup.style.display = "none";
                if (helpContent) helpContent.style.display = "none";
            };
        }
        if (helpBtn && helpContent) {
            helpBtn.onclick = () => {
                const isHidden = helpContent.style.display === "none" || helpContent.style.display === "";
                helpContent.style.display = isHidden ? "block" : "none";
            };
        }

        window.addEventListener('click', (event) => {
            if (instructionsModal && event.target == instructionsModal) {
                instructionsModal.style.display = "none";
            }
        });


        function dragElement(elmnt) {
            let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
            const header = document.getElementById(elmnt.id + "-header");
            if (header) { header.onmousedown = dragMouseDown; }
            else { elmnt.onmousedown = dragMouseDown; }

            function dragMouseDown(e) {
                if (e.target.closest('#helpContent')) {
                    return;
                }
                e = e || window.event;
                e.preventDefault();
                pos3 = e.clientX;
                pos4 = e.clientY;
                document.onmouseup = closeDragElement;
                document.onmousemove = elementDrag;
            }

            function elementDrag(e) {
                e = e || window.event;
                e.preventDefault();
                pos1 = pos3 - e.clientX;
                pos2 = pos4 - e.clientY;
                pos3 = e.clientX;
                pos4 = e.clientY;
                elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
                elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
            }

            function closeDragElement() {
                document.onmouseup = null;
                document.onmousemove = null;
            }
        }
        if (calculatorPopup) dragElement(calculatorPopup);
    }
};
function sppExamToast(message) {
    const host = document.fullscreenElement || document.body;
    const t = document.createElement('div');
    t.textContent = message;
    t.style.cssText = 'position:fixed;left:50%;top:24px;transform:translateX(-50%);z-index:2147483647;' +
        'background:#992c25;color:#fff;padding:12px 22px;border-radius:8px;font-weight:600;' +
        'box-shadow:0 6px 24px rgba(0,0,0,.25);max-width:90%;text-align:center;font-size:15px;';
    host.appendChild(t);
    setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 3500);
}

function sppExamConfirm(message, onYes, onNo) {
    const host = document.fullscreenElement || document.body;
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.55);' +
        'display:flex;align-items:center;justify-content:center;';
    const box = document.createElement('div');
    box.style.cssText = 'background:#fff;color:#1a1a1a;max-width:420px;width:90%;border-radius:12px;' +
        'padding:24px;box-shadow:0 12px 40px rgba(0,0,0,.3);';
    const p = document.createElement('p');
    p.textContent = message;
    p.style.cssText = 'margin:0 0 20px;font-size:16px;line-height:1.5;';
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:12px;justify-content:flex-end;';
    const no = document.createElement('button');
    no.type = 'button';
    no.textContent = 'Cancel';
    no.style.cssText = 'padding:10px 18px;border:1px solid #ccc;background:#f3f3f3;border-radius:8px;' +
        'cursor:pointer;font-weight:600;font-size:14px;';
    const yes = document.createElement('button');
    yes.type = 'button';
    yes.textContent = 'OK';
    yes.style.cssText = 'padding:10px 18px;border:none;background:#992c25;color:#fff;border-radius:8px;' +
        'cursor:pointer;font-weight:600;font-size:14px;';
    const close = () => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); };
    no.onclick = () => { close(); if (typeof onNo === 'function') onNo(); };
    yes.onclick = () => { close(); if (typeof onYes === 'function') onYes(); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) { close(); if (typeof onNo === 'function') onNo(); } });
    row.appendChild(no);
    row.appendChild(yes);
    box.appendChild(p);
    box.appendChild(row);
    overlay.appendChild(box);
    host.appendChild(overlay);
    yes.focus();
}

window.testManager = testManager;
