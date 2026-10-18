document.addEventListener('DOMContentLoaded', function() {
    const viewAllBtn = document.getElementById('viewAllBtn');
    const searchForm = document.getElementById('searchForm');
    const emailSearchInput = document.getElementById('emailSearch');
    const paymentIdSearchInput = document.getElementById('paymentIdSearch');
    const purchaseDataContainer = document.getElementById('purchaseDataContainer');
    const purchaseTableBody = document.getElementById('purchaseTableBody');
    const messageArea = document.getElementById('messageArea');

    viewAllBtn.addEventListener('click', fetchAllPurchases);
    searchForm.addEventListener('submit', handleSearch);

    function fetchAllPurchases() {
        fetch('/get_all_purchases')
            .then(handleResponse)
            .then(data => {
                displayPurchases(data);
            })
            .catch(handleError);
    }

    function handleSearch(event) {
        event.preventDefault();
        const email = emailSearchInput.value.trim();
        const paymentId = paymentIdSearchInput.value.trim();

        if (!email || !paymentId) {
            showMessage('Please enter both email and payment ID.', 'error');
            return;
        }

        fetch(`/search_purchase?email=${encodeURIComponent(email)}&payment_id=${encodeURIComponent(paymentId)}`)
            .then(handleResponse)
            .then(data => {
                if (data.length > 0) {
                    displayPurchases(data, data[0].payment_id);
                } else {
                    showMessage('No purchase found for this Email and Payment ID.', 'info');
                    purchaseDataContainer.style.display = 'none';
                }
            })
            .catch(handleError);
    }

    function displayPurchases(purchases, highlightPaymentId = null) {
        purchaseTableBody.innerHTML = '';
        messageArea.innerHTML = '';

        if (!purchases || purchases.length === 0) {
            showMessage('No purchase data found.', 'info');
            purchaseDataContainer.style.display = 'none';
            return;
        }

        purchases.forEach(purchase => {
            const row = purchaseTableBody.insertRow();
            if (purchase.payment_id === highlightPaymentId) {
                row.classList.add('highlight');
            }

            row.innerHTML = `
                <td>${purchase.email || 'N/A'}</td>
                <td>${purchase.username || 'N/A'}</td>
                <td>${purchase.phone || 'N/A'}</td>
                <td>${purchase.course_code || 'N/A'}</td>
                <td>${purchase.title || 'N/A'}</td>
                <td>${purchase.price || 0}</td>
                <td>${purchase.final_price || 0}</td>
                <td>${purchase.payment_id || 'N/A'}</td>
                <td>${purchase.payment_date ? new Date(purchase.payment_date).toLocaleString() : 'N/A'}</td>
                <td>${purchase.status || 'N/A'}</td>
                <td>
                    ${purchase.status === 'Pending' ? `<button class="delete-btn" data-id="${purchase.id}">Delete</button>` : 'N/A'}
                </td>
            `;
        });

        purchaseDataContainer.style.display = 'block';
        addDeleteEventListeners();
    }

    function addDeleteEventListeners() {
        document.querySelectorAll('.delete-btn').forEach(button => {
            button.addEventListener('click', function() {
                const purchaseId = this.dataset.id;
                if (confirm('Are you sure you want to delete this pending purchase? This action cannot be undone.')) {
                    deletePurchase(purchaseId);
                }
            });
        });
    }

    function deletePurchase(purchaseId) {
        fetch(`/delete_purchase/${purchaseId}`, {
            method: 'DELETE',
        })
        .then(handleResponse)
        .then(data => {
            showMessage(data.message, 'success');
            fetchAllPurchases();
        })
        .catch(handleError);
    }

    function handleResponse(response) {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || 'Network response was not ok');
            });
        }
        return response.json();
    }

    function handleError(error) {
        console.error('Fetch Error:', error);
        showMessage(error.message || 'An error occurred. Please check the console.', 'error');
    }

    function showMessage(message, type = 'info') {
        messageArea.innerHTML = `<p class="${type}">${message}</p>`;
        messageArea.style.color = type === 'error' ? 'red' : (type === 'success' ? 'green' : 'black');
    }
});
