const PAGE_DATA = document.getElementById('pageData').dataset;

    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            window.location.replace(PAGE_DATA.indexUrl);
        }, 1000);
    });
