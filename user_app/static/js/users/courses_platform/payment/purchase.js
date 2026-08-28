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
