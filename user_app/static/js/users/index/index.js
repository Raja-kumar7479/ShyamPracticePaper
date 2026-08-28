document.addEventListener('DOMContentLoaded', function () {
            document.querySelectorAll('.faq-question').forEach(q => {
                q.addEventListener('click', () => {
                    q.classList.toggle('active');
                    q.nextElementSibling.classList.toggle('active');
                });
            });

            const revealTargets = document.querySelectorAll(
                '[data-reveal], .exam-card, .feature-card, .mock-point, .placement-item, .faq-item, .testimonial-card, .step-card'
            );
            if ('IntersectionObserver' in window) {
                revealTargets.forEach((el, i) => {
                    el.classList.add('reveal-init');
                    el.style.transitionDelay = `${Math.min((i % 6) * 70, 350)}ms`;
                });
                const revealObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('reveal-visible');
                            revealObserver.unobserve(entry.target);
                        }
                    });
                }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
                revealTargets.forEach(el => revealObserver.observe(el));
            }
        });
