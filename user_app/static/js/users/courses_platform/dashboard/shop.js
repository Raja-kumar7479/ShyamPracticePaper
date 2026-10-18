function filterGrid(val) {
        const input = (val || '').trim().toLowerCase();
        const items = document.querySelectorAll('.filter-item');
        let visibleCount = 0;

        items.forEach(item => {
            const title = item.getAttribute('data-title') || '';
            const match = title.includes(input);
            item.style.display = match ? 'flex' : 'none';
            if (match) visibleCount++;
        });

        document.querySelectorAll('.js-shop-search').forEach(box => {
            if (box.value !== val) box.value = val;
        });

        const noResults = document.getElementById('noResults');
        if (noResults) noResults.style.display = (visibleCount === 0 && items.length > 0) ? 'block' : 'none';
    }


