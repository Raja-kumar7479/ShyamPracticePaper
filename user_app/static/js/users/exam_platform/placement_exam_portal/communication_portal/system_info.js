document.addEventListener('DOMContentLoaded', function() {
        const wrapper = document.getElementById('slider-wrapper');
        const track = document.getElementById('slider-track');
        let slides = Array.from(track.children);
        const nextButton = document.getElementById('slider-next');
        const prevButton = document.getElementById('slider-prev');
        const dots = document.querySelectorAll('[data-slide-to]');
        let currentSlide = 0;
        let autoSlide;
        let startX = 0; let currentX = 0; let isDragging = false;
        const SWIPE_THRESHOLD = 40;

        function setSlideWidths() {
            const width = Math.max(1, wrapper.clientWidth);
            slides.forEach(s => s.style.minWidth = width + 'px');
            track.style.transform = 'translateX(-' + width * currentSlide + 'px)';
        }
        function goToSlide(index) {
            index = Math.max(0, Math.min(index, slides.length - 1));
            const width = wrapper.clientWidth || track.getBoundingClientRect().width;
            track.style.transition = 'transform 0.4s ease-in-out';
            track.style.transform = 'translateX(-' + width * index + 'px)';
            dots.forEach((d, i) => { d.classList.toggle('active', i === index); });
            currentSlide = index;
            prevButton.classList.toggle('disabled', index === 0);
            nextButton.classList.toggle('disabled', index === slides.length - 1);
        }
        function startAutoSlide() { clearInterval(autoSlide); autoSlide = setInterval(() => { if (currentSlide < slides.length - 1) goToSlide(currentSlide + 1); else goToSlide(0); }, 4000); }
        function resetAutoSlide() { clearInterval(autoSlide); startAutoSlide(); }

        nextButton.onclick = function() { if (currentSlide < slides.length - 1) goToSlide(currentSlide + 1); resetAutoSlide(); };
        prevButton.onclick = function() { if (currentSlide > 0) goToSlide(currentSlide - 1); resetAutoSlide(); };
        dots.forEach((d, i) => d.onclick = function() { goToSlide(i); resetAutoSlide(); });

        window.addEventListener('resize', setSlideWidths);
        wrapper.addEventListener('touchstart', function(e) { if (!e.touches || e.touches.length === 0) return; startX = e.touches[0].clientX; currentX = startX; isDragging = true; track.style.transition = 'none'; }, {passive:true});
        wrapper.addEventListener('touchmove', function(e) { if (!isDragging || !e.touches || e.touches.length === 0) return; currentX = e.touches[0].clientX; const dx = currentX - startX; const width = wrapper.clientWidth; const translate = -currentSlide * width + dx; track.style.transform = 'translateX(' + translate + 'px)'; }, {passive:true});
        wrapper.addEventListener('touchend', function(e) { if (!isDragging) return; isDragging = false; const dx = currentX - startX; if (dx > SWIPE_THRESHOLD && currentSlide > 0) goToSlide(currentSlide - 1); else if (dx < -SWIPE_THRESHOLD && currentSlide < slides.length - 1) goToSlide(currentSlide + 1); else goToSlide(currentSlide); resetAutoSlide(); });

        setSlideWidths(); startAutoSlide();
    });
