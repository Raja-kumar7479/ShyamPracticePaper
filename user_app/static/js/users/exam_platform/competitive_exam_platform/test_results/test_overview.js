const PAGE_DATA = document.getElementById('pageData').dataset;

    document.addEventListener('DOMContentLoaded', function() {
        const viewSummaryBtn = document.getElementById('viewSummaryBtn');
        if (viewSummaryBtn) {
            viewSummaryBtn.addEventListener('click', function() {
                const finalUrl = PAGE_DATA.resultUrl ||
                                 (PAGE_DATA.openMockTestSectionUrl + '?action=show_result');
                window.open(finalUrl, '_blank');
                window.close();
            });
        }
        const circle = document.getElementById('progressCircle');
        if (circle) {
            const value = circle.getAttribute('data-value');
            circle.style.setProperty('--value', value);
        }
    });
