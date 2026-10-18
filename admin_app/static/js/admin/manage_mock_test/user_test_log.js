document.addEventListener('DOMContentLoaded', function() {
    const viewLogsBtn = document.getElementById('viewLogsBtn');
    const logDataContainer = document.getElementById('logDataContainer');
    const viewDataContainer = document.getElementById('viewDataContainer');
    const testLogTableBody = document.querySelector('#testLogTable tbody');
    const paginationContainer = document.getElementById('pagination');
    const liveTestAttemptCountSpan = document.getElementById('liveTestAttemptCount');
    const flashMessagesContainer = document.getElementById('flash-messages');

    viewLogsBtn.addEventListener('click', function() {
        fetchTestLogData(1);
        viewDataContainer.style.display = 'none';
        logDataContainer.style.display = 'block';
    });

    function fetchTestLogData(page) {
        fetch(`/get_test_log_data?page=${page}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showFlashMessage(data.error, 'danger');
                    return;
                }

                testLogTableBody.innerHTML = '';

                if (data.test_logs.length === 0) {
                    testLogTableBody.innerHTML = '<tr><td colspan="6" class="text-center">No user test log data available.</td></tr>';
                } else {
                    data.test_logs.forEach(log => {
                        const startTime = log.start_time ? new Date(log.start_time).toLocaleString() : 'N/A';
                        const endTime = log.end_time ? new Date(log.end_time).toLocaleString() : 'N/A';
                        const row = `<tr>
                            <td>${log.email}</td>
                            <td>${log.username}</td>
                            <td>${log.test_id}</td>
                            <td>${log.test_key || 'N/A'}</td>
                            <td>${startTime}</td>
                            <td>${endTime}</td>
                        </tr>`;
                        testLogTableBody.insertAdjacentHTML('beforeend', row);
                    });
                }

                setupPagination(data.total_pages, data.current_page);
            })
            .catch(error => {
                console.error('Error fetching test log data:', error);
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
                fetchTestLogData(currentPage - 1);
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
                fetchTestLogData(i);
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
                fetchTestLogData(currentPage + 1);
            }
        });
        nextLi.appendChild(nextA);
        paginationContainer.appendChild(nextLi);
    }

    function fetchLiveCount() {
        fetch('/get_unique_test_attempts_count')
            .then(response => response.json())
            .then(data => {
                if (data.unique_attempts_count !== undefined) {
                    const currentCount = parseInt(liveTestAttemptCountSpan.textContent);
                    if(data.unique_attempts_count !== currentCount) {
                        liveTestAttemptCountSpan.textContent = data.unique_attempts_count;
                        liveTestAttemptCountSpan.classList.add('fade-in');
                        setTimeout(() => {
                            liveTestAttemptCountSpan.classList.remove('fade-in');
                        }, 500);
                    }
                } else {
                    console.error('API response missing unique_attempts_count:', data);
                }
            })
            .catch(error => {
                console.error('Error fetching live count:', error);
            });
    }

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

    fetchLiveCount();
    setInterval(fetchLiveCount, 10000);
});