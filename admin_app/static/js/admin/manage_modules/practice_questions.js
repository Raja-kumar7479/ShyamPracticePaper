document.addEventListener('DOMContentLoaded', function () {
    const addForm = document.getElementById('add-question-form');
    const tableBody = document.getElementById('questions-table-body');
    const courseSelect = document.getElementById('code');
    const existingQuestionsSection = document.getElementById('existing-questions-section');
    const selectedCourseCodeSpan = document.getElementById('selected-course-code');

    const updateUrlBase = tableBody.dataset.updateUrl;
    const deleteUrlBase = tableBody.dataset.deleteUrl;

    const showAlert = (message, category = 'success') => {
        const container = document.getElementById('alert-container');
        if (!container) return;
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${category} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.style.position = 'fixed';
        alertDiv.style.top = '1rem';
        alertDiv.style.right = '1rem';
        alertDiv.style.zIndex = '1050';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        document.body.appendChild(alertDiv);
        setTimeout(() => alertDiv.remove(), 5000);
    };

    const createTableRow = (q) => {
        return `
            <tr id="row-${q.id}">
                <td>${q.id}</td>
                <td><span class="badge bg-primary">${q.code}</span></td>
                <td><span class="badge bg-secondary">${q.section}</span></td>
                <td class="editable" contenteditable="true" data-field="title" data-id="${q.id}">${q.title}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-danger delete-btn" data-id="${q.id}" title="Delete Question">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </td>
            </tr>
        `;
    };

    const renderTable = (questions) => {
        tableBody.innerHTML = '';
        if (questions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center p-4">No practice questions found for this course.</td></tr>';
            return;
        }
        questions.forEach(q => {
            tableBody.insertAdjacentHTML('beforeend', createTableRow(q));
        });
    };

    const fetchQuestionsForCode = (code) => {
        tableBody.innerHTML = '<tr><td colspan="5" class="text-center p-4"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></td></tr>';
        existingQuestionsSection.classList.remove('d-none');
        selectedCourseCodeSpan.textContent = code;

        fetch(`/api/questions_by_code?code=${code}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderTable(data.questions);
            } else {
                showAlert(data.message || 'Could not fetch questions.', 'danger');
                tableBody.innerHTML = '<tr><td colspan="5" class="text-center p-4 text-danger">Error loading questions.</td></tr>';
            }
        })
        .catch(() => {
            showAlert('Network error. Please try again.', 'danger');
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center p-4 text-danger">Network error.</td></tr>';
        });
    };

    courseSelect.addEventListener('change', function() {
        const selectedCode = this.value;
        if (!selectedCode) {
            existingQuestionsSection.classList.add('d-none');
            return;
        }
        fetchQuestionsForCode(selectedCode);
    });

    const sectionInput = addForm.querySelector('#section');
    const sectionOpens = document.getElementById('sectionOpens');
    function paintSectionOpens() {
        if (!sectionInput || !sectionOpens) return;
        const v = (sectionInput.value || '').toLowerCase();
        if (!v.trim()) { sectionOpens.textContent = ''; return; }
        const mode = v.includes('year') ? 'year-wise' : (v.includes('topic') ? 'topic-wise' : 'subject-wise');
        sectionOpens.textContent = `Opens ${mode} browsing.`;
    }
    if (sectionInput) sectionInput.addEventListener('input', paintSectionOpens);

    addForm.addEventListener('submit', function (e) {
        e.preventDefault();
        const formData = new FormData(this);
        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Adding...';

        fetch(this.action, {
            method: 'POST',
            body: new URLSearchParams(formData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('Format added.');
                const currentCode = courseSelect.value;
                if (data.question.code === currentCode) {
                    const noDataRow = tableBody.querySelector('td[colspan="5"]');
                    if (noDataRow) noDataRow.parentElement.remove();
                    tableBody.insertAdjacentHTML('afterbegin', createTableRow(data.question));
                }
                const sectionSelect = addForm.querySelector('#section');
                addForm.reset();
                courseSelect.value = currentCode;
                sectionSelect.value = "";
            } else {
                showAlert(data.message || 'An error occurred.', 'danger');
            }
        })
        .catch(() => showAlert('Network error. Please try again.', 'danger'))
        .finally(() => {
            submitButton.disabled = false;
            submitButton.innerHTML = '<i class="fas fa-plus me-1"></i> Add Format';
        });
    });

    const updateField = (cell) => {
        const originalValue = cell.dataset.originalValue;
        const currentValue = cell.textContent.trim();
        cell.blur();

        if (originalValue !== null && originalValue !== currentValue) {
            const questionId = cell.dataset.id;
            const field = cell.dataset.field;

            fetch(updateUrlBase.replace('0', questionId), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ field, value: currentValue })
            })
            .then(response => response.json())
            .then(data => {
                if(data.success) {
                    showAlert('Update successful.');
                    cell.dataset.originalValue = currentValue;
                } else {
                    showAlert(data.message || 'Update failed.', 'danger');
                    cell.textContent = originalValue;
                }
            })
            .catch(() => {
                showAlert('Network error during update.', 'danger');
                cell.textContent = originalValue;
            });
        }
    };

    tableBody.addEventListener('focusin', (e) => {
        if (e.target.classList.contains('editable')) {
            e.target.dataset.originalValue = e.target.textContent.trim();
        }
    });

    tableBody.addEventListener('focusout', (e) => {
        if (e.target.classList.contains('editable')) {
            updateField(e.target);
        }
    });

    tableBody.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.target.classList.contains('editable')) {
            e.preventDefault();
            updateField(e.target);
        } else if (e.key === 'Escape' && e.target.classList.contains('editable')) {
            e.target.textContent = e.target.dataset.originalValue;
            e.target.blur();
        }
    });

    const deleteQuestion = (questionId, button) => {
        button.disabled = true;
        fetch(deleteUrlBase.replace('0', questionId), { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if(data.success) {
                showAlert('Question deleted.');
                document.getElementById(`row-${questionId}`).remove();
                if (tableBody.rows.length === 0) {
                   renderTable([]);
                }
            } else {
                showAlert(data.message || 'Delete failed.', 'danger');
                button.disabled = false;
            }
        })
        .catch(() => {
            showAlert('Network error during delete.', 'danger');
            button.disabled = false;
        });
    };

    tableBody.addEventListener('click', function (e) {
        const deleteButton = e.target.closest('.delete-btn');
        if (deleteButton) {
            const questionId = deleteButton.dataset.id;
            const row = deleteButton.closest('tr');
            const title = row ? (row.querySelector('[data-field="title"]') || {}).textContent : '';
            const ask = window.adminConfirm ? window.adminConfirm({ tone: 'danger', title: `Delete the format "${(title || '').trim()}"?`,
                message: 'Students will no longer see this practice format in the course.', note: 'This cannot be undone.', confirmText: 'Delete format' })
                : Promise.resolve(confirm('Delete this format?'));
            ask.then(ok => { if (ok) deleteQuestion(questionId, deleteButton); });
        }
    });
});