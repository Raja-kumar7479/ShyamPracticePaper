document.addEventListener('DOMContentLoaded', function () {
    const testIdSelect = document.getElementById('test-id-select');
    const codeSelect = document.getElementById('code-select');
    const typeSelect = document.getElementById('type-select');
    const setInitialBtn = document.getElementById('set-initial-btn');
    const mainForm = document.getElementById('main-upload-form');
    const initialSelectionDiv = document.getElementById('initial-selection');
    const existingNotesSection = document.getElementById('existing-notes-section');
    const existingNotesContainer = document.getElementById('existing-notes-container');
    const notesListUl = document.getElementById('notes-list-ul');
    const noNotesMsg = document.getElementById('no-notes-message');

    const headingSection = document.getElementById('heading-selection-section');
    const headingSelect = document.getElementById('heading-select');
    const headingInputContainer = document.getElementById('heading-input-container');
    const headingInput = document.getElementById('heading-input');

    const subHeadingSection = document.getElementById('sub-heading-selection-section');
    const subHeadingSelect = document.getElementById('sub-heading-select');
    const subHeadingInputContainer = document.getElementById('sub-heading-input-container');
    const subHeadingInput = document.getElementById('sub-heading-input');

    const titleEntrySection = document.getElementById('title-entry-section');

    const showAlert = (message, category = 'success') => {
        const container = document.getElementById('alert-container');
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${category} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        container.appendChild(alertDiv);
        const bsAlert = new bootstrap.Alert(alertDiv);
        setTimeout(() => bsAlert.close(), 5000);
    };

    const renderNote = (note) => {
        const newItem = document.createElement('li');
        newItem.className = 'list-group-item d-flex justify-content-between align-items-center';
        newItem.id = `note-item-${note.id}`;
        newItem.innerHTML = `
            <div>
                <strong>${note.title}</strong><br>
                <small class="text-muted">${note.heading} → ${note.sub_heading}</small>
            </div>
            <div class="text-end">
                <a href="${note.file_url}" target="_blank" class="btn btn-sm btn-outline-primary">View</a>
                <button class="btn btn-sm btn-danger delete-note-btn" data-note-id="${note.id}">Delete</button>
            </div>
        `;
        return newItem;
    };

    testIdSelect.addEventListener('change', () => {
        const testId = testIdSelect.value;
        codeSelect.disabled = true;
        codeSelect.innerHTML = '<option>Loading...</option>';
        if (!testId) return;

        fetch(`/api/code_for_section/${testId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.code) {
                    codeSelect.innerHTML = `<option value="${data.code}">${data.code}</option>`;
                    codeSelect.disabled = false;
                } else {
                    showAlert(data.message || 'Could not find code for this Test ID.', 'warning');
                    codeSelect.innerHTML = '<option selected disabled value="">Select Test ID first</option>';
                }
            })
            .catch((error) => {
                console.error('Fetch Error:', error);
                showAlert('Error fetching code.', 'danger');
                codeSelect.innerHTML = '<option selected disabled value="">Select Test ID first</option>';
            });
    });

    setInitialBtn.addEventListener('click', () => {
        const testId = testIdSelect.value;
        const code = codeSelect.value;
        const type = typeSelect.value;

        if (!testId || !code || !type) {
            showAlert('Please select a Test ID, Code, and Type.', 'warning');
            return;
        }

        notesListUl.innerHTML = '<li>Loading...</li>';
        existingNotesSection.classList.remove('hidden-section');

        fetch(`/api/notes?test_id=${testId}&code=${code}&type=${type}`)
            .then(response => {
                 if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                notesListUl.innerHTML = '';
                if (data.success && data.notes.length > 0) {
                    noNotesMsg.classList.add('d-none');
                    data.notes.forEach(note => notesListUl.appendChild(renderNote(note)));
                } else {
                    noNotesMsg.classList.remove('d-none');
                }

                document.getElementById('form-test-id').value = testId;
                document.getElementById('form-code').value = code;
                document.getElementById('form-type').value = type;

                initialSelectionDiv.classList.add('hidden-section');
                mainForm.classList.remove('hidden-section');
                headingSection.classList.remove('hidden-section');
                fetchHeadings(testId, code, type);
            })
            .catch(err => {
                console.error('Fetch Error:', err);
                showAlert('Failed to fetch notes.', 'danger');
                notesListUl.innerHTML = '';
            });
    });

    const fetchHeadings = (testId, code, type) => {
        fetch(`/api/notes/headings?test_id=${testId}&code=${code}&type=${type}`)
            .then(res => res.json())
            .then(data => {
                headingSelect.innerHTML = '<option value="">Select Existing or Add New</option>';
                if(data.success) {
                    data.headings.forEach(h => headingSelect.add(new Option(h, h)));
                }
                headingSelect.add(new Option('--- Add New Heading ---', 'add_new'));
            });
    };

    headingSelect.addEventListener('change', () => {
        subHeadingSection.classList.add('hidden-section');
        titleEntrySection.classList.add('hidden-section');
        subHeadingSelect.innerHTML = '';
        if (headingSelect.value === 'add_new') {
            headingInputContainer.classList.remove('hidden-section');
            subHeadingSection.classList.remove('hidden-section');
            subHeadingSelect.innerHTML = '<option value="add_new" selected>--- Add New Sub-Heading ---</option>';
            subHeadingSelect.dispatchEvent(new Event('change'));
        } else if (headingSelect.value) {
            headingInputContainer.classList.add('hidden-section');
            headingInput.value = '';
            subHeadingSection.classList.remove('hidden-section');
            fetchSubHeadings(testIdSelect.value, codeSelect.value, typeSelect.value, headingSelect.value);
        }
    });

    const fetchSubHeadings = (testId, code, type, heading) => {
        fetch(`/api/notes/sub_headings?test_id=${testId}&code=${code}&type=${type}&heading=${heading}`)
            .then(res => res.json())
            .then(data => {
                subHeadingSelect.innerHTML = '<option value="">Select Existing or Add New</option>';
                if(data.success) {
                    data.sub_headings.forEach(sh => subHeadingSelect.add(new Option(sh, sh)));
                }
                subHeadingSelect.add(new Option('--- Add New Sub-Heading ---', 'add_new'));
            });
    };

    subHeadingSelect.addEventListener('change', () => {
        titleEntrySection.classList.add('hidden-section');
        if(subHeadingSelect.value === 'add_new') {
            subHeadingInputContainer.classList.remove('hidden-section');
            titleEntrySection.classList.remove('hidden-section');
        } else if (subHeadingSelect.value) {
            subHeadingInputContainer.classList.add('hidden-section');
            subHeadingInput.value = '';
            titleEntrySection.classList.remove('hidden-section');
        }
    });

    mainForm.addEventListener('submit', function (event) {
        event.preventDefault();
        const submitButton = this.querySelector('button[type="submit"]');
        const originalButtonText = submitButton.textContent;
        submitButton.disabled = true;
        submitButton.textContent = 'Uploading...';
        const formData = new FormData(this);

        fetch(this.action, { method: 'POST', body: formData })
        .then(response => {
             if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showAlert('Note added successfully!', 'success');
                const newNoteElement = renderNote(data.note);
                if (notesListUl.firstChild) {
                    notesListUl.insertBefore(newNoteElement, notesListUl.firstChild);
                } else {
                    notesListUl.appendChild(newNoteElement);
                }
                noNotesMsg.classList.add('d-none');
                this.reset();
                headingSelect.value = '';
                headingSelect.dispatchEvent(new Event('change'));

            } else {
                showAlert(data.message || 'An unknown error occurred.', 'danger');
            }
        })
        .catch(error => {
            console.error('Submit Error:', error);
            showAlert('A network or server error occurred. Please try again.', 'danger');
        })
        .finally(() => {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonText;
        });
    });

    existingNotesContainer.addEventListener('click', function(event) {
        const deleteButton = event.target.closest('.delete-note-btn');
        if (deleteButton) {
            const noteId = deleteButton.getAttribute('data-note-id');
            const askNote = window.adminConfirm ? window.adminConfirm({ tone: 'danger', title: 'Delete this note?', message: 'Students will no longer see it, and its uploaded file is removed.', note: 'This cannot be undone.', confirmText: 'Delete note' }) : Promise.resolve(confirm('Delete this note?'));
            askNote.then(function (okNote) {
                if (!okNote) return;
                fetch(`/api/note/delete/${noteId}`, { method: 'POST' })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Server responded with status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        showAlert('Note deleted successfully.', 'success');
                        document.getElementById(`note-item-${noteId}`).remove();
                        if (notesListUl.children.length === 0) {
                            noNotesMsg.classList.remove('d-none');
                        }
                    } else {
                        showAlert(data.message || 'Failed to delete note.', 'danger');
                    }
                })
                .catch(error => {
                    console.error('Delete Error:', error);
                    showAlert('A server error occurred during deletion.', 'danger');
                });
            });
        }
    });
});