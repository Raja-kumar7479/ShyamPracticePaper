document.addEventListener('DOMContentLoaded', () => {
    const timerEl = document.getElementById('live-timer');
    const dateEl = document.getElementById('date-display');
    const quoteEl = document.getElementById('motivational-quote');

    const quotes = [
        "The only way to do great work is to love what you do.",
        "Believe you can and you're halfway there.",
        "The secret of getting ahead is getting started.",
        "Your limitation is only your imagination.",
        "Push yourself, because no one else is going to do it for you."
    ];

    function updateTime() {
        const now = new Date();
        if (timerEl) {
            timerEl.textContent = now.toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
        }
        if (dateEl) {
            dateEl.textContent = now.toLocaleDateString([], {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
            });
        }
    }

    function updateQuote() {
        if (quoteEl) {
            quoteEl.textContent = quotes[Math.floor(Math.random() * quotes.length)];
        }
    }

    updateTime();
    updateQuote();

    if (timerEl || dateEl) setInterval(updateTime, 1000);
    if (quoteEl) setInterval(updateQuote, 30000);
});
