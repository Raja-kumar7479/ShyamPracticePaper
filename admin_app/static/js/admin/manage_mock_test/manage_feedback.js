document.addEventListener('DOMContentLoaded', function() {
    const viewFeedbackBtn = document.getElementById('viewFeedbackBtn');
    const feedbackDataContainer = document.getElementById('feedbackDataContainer');
    const viewDataContainer = document.getElementById('viewDataContainer');
    const feedbackTableBody = document.querySelector('#feedbackTable tbody');
    const paginationContainer = document.getElementById('pagination');
    const truncateFeedbackBtn = document.getElementById('truncateFeedbackBtn');
    const flashMessagesContainer = document.getElementById('flash-messages');

    viewFeedbackBtn.addEventListener('click', function() {
        fetchFeedbackData(1);
        viewDataContainer.style.display = 'none';
        feedbackDataContainer.style.display = 'block';
    });

    function fetchFeedbackData(page) {
        fetch(`/get_feedback_data?page=${page}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showFlashMessage(data.error, 'danger');
                    return;
                }

                feedbackTableBody.innerHTML = '';

                if (data.feedbacks.length === 0) {
                    feedbackTableBody.innerHTML = '<tr><td colspan="9" class="text-center">No feedback data available.</td></tr>';
                } else {
                    data.feedbacks.forEach(feedback => {
                        const row = `<tr>
                            <td>${feedback.id}</td>
                            <td>${feedback.test_id}</td>
                            <td>${feedback.test_key || 'N/A'}</td>
                            <td>${feedback.email}</td>
                            <td>${feedback.feedback_software}</td>
                            <td>${feedback.feedback_content}</td>
                            <td>${feedback.feedback_speed}</td>
                            <td>${feedback.suggestions}</td>
                            <td>${new Date(feedback.submission_time).toLocaleString()}</td>
                        </tr>`;
                        feedbackTableBody.insertAdjacentHTML('beforeend', row);
                    });
                }

                setupPagination(data.total_pages, data.current_page);
            })
            .catch(error => {
                console.error('Error fetching feedback data:', error);
                showFlashMessage('An error occurred while fetching data.', 'danger');
            });
    }

    function setupPagination(totalPages, currentPage) {
        paginationContainer.innerHTML = '';
        if (totalPages <= 1) return;

        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        const prevA = document.createElement('a');
        prevA.className = 'page-link';
        prevA.href = '#';
        prevA.innerText = 'Previous';
        prevA.addEventListener('click', (e) => {
            e.preventDefault();
            if (currentPage > 1) {
                fetchFeedbackData(currentPage - 1);
            }
        });
        prevLi.appendChild(prevA);
        paginationContainer.appendChild(prevLi);

        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentPage ? 'active' : ''}`;
            const a = document.createElement('a');
            a.className = 'page-link';
            a.href = '#';
            a.innerText = i;
            a.addEventListener('click', (e) => {
                e.preventDefault();
                fetchFeedbackData(i);
            });
            li.appendChild(a);
            paginationContainer.appendChild(li);
        }

        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        const nextA = document.createElement('a');
        nextA.className = 'page-link';
        nextA.href = '#';
        nextA.innerText = 'Next';
        nextA.addEventListener('click', (e) => {
            e.preventDefault();
            if (currentPage < totalPages) {
                fetchFeedbackData(currentPage + 1);
            }
        });
        nextLi.appendChild(nextA);
        paginationContainer.appendChild(nextLi);
    }

    truncateFeedbackBtn.addEventListener('click', function() {
        if (confirm("Are you absolutely sure you want to DELETE ALL FEEDBACK DATA? This action cannot be undone.")) {
            fetch('/truncate_feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                showFlashMessage(data.message, data.success ? 'success' : 'danger');
                if (data.success) {
                    feedbackTableBody.innerHTML = '<tr><td colspan="9" class="text-center">No feedback data available.</td></tr>';
                    paginationContainer.innerHTML = '';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showFlashMessage('An error occurred while trying to delete feedback data.', 'danger');
            });
        }
    });

    function showFlashMessage(message, category) {
        const flashDiv = document.createElement('div');
        flashDiv.className = `alert alert-${category} alert-dismissible fade show`;
        flashDiv.role = 'alert';
        flashDiv.innerHTML = `
            ${message}
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">&times;</span>
            </button>
        `;
        flashMessagesContainer.appendChild(flashDiv);
        setTimeout(() => {
            flashDiv.remove();
        }, 5000);
    }
});