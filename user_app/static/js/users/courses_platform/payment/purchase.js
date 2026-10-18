function toggleSidebar() {
      const sidebar = document.getElementById("sidebar");
      const backdrop = document.getElementById("sidebarBackdrop");
      if (!sidebar) return;
      const isOpen = sidebar.classList.toggle("show");
      if (backdrop) backdrop.classList.toggle("show", isOpen);
      document.body.style.overflow = isOpen ? "hidden" : "";
      const toggleBtn = document.querySelector(".topbar .toggle-btn");
      if (toggleBtn) toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        const sidebar = document.getElementById('sidebar');
        if (sidebar && sidebar.classList.contains('show')) toggleSidebar();
      }
    });

    document.addEventListener('DOMContentLoaded', () => {
        const searchInput = document.getElementById('purchaseSearch');
        if (searchInput) {
            const noResultsMessage = document.getElementById('noResultsMessage');
            const sectionCards = document.querySelectorAll('.purchase-section-card');

            searchInput.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                let totalVisibleItems = 0;

                sectionCards.forEach(card => {
                    let sectionHasVisibleItems = false;
                    const items = card.querySelectorAll('.purchase-item');

                    items.forEach(item => {
                        const titleEl = item.querySelector('h4, strong');
                        const subtitleEl = item.querySelector('p');
                        const title = titleEl ? titleEl.textContent.toLowerCase() : '';
                        const subtitle = subtitleEl ? subtitleEl.textContent.toLowerCase() : '';

                        if (title.includes(searchTerm) || subtitle.includes(searchTerm)) {
                            item.style.display = 'flex';
                            sectionHasVisibleItems = true;
                            totalVisibleItems++;
                        } else {
                            item.style.display = 'none';
                        }
                    });

                    if (sectionHasVisibleItems) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });

                if (totalVisibleItems === 0 && searchTerm.length > 0) {
                    noResultsMessage.style.display = 'block';
                } else {
                    noResultsMessage.style.display = 'none';
                }
            });
        }
    });

document.addEventListener('DOMContentLoaded', function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute('content') : '';
    document.querySelectorAll('.pend__check').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var row = btn.closest('.pend__row');
            var msg = row.querySelector('.pend__msg');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Asking Razorpay...';
            fetch('/api/payment/check/' + encodeURIComponent(btn.dataset.order), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
                body: '{}'
            }).then(function (r) { return r.json(); }).then(function (d) {
                msg.hidden = false;
                msg.textContent = d.message || d.error || 'No answer.';
                msg.className = 'pend__msg ' + (d.status === 'paid' ? 'is-ok' : (d.status === 'failed' ? 'is-bad' : 'is-wait'));
                if (d.status === 'paid') {
                    btn.innerHTML = '<i class="fas fa-circle-check"></i> Access opened';
                    setTimeout(function () { window.location.reload(); }, 1800);
                    return;
                }
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-rotate"></i> Check again';
            }).catch(function () {
                msg.hidden = false; msg.className = 'pend__msg is-wait';
                msg.textContent = 'Could not reach the server. Try again.';
                btn.disabled = false; btn.innerHTML = '<i class="fas fa-rotate"></i> Check again';
            });
        });
    });
});
