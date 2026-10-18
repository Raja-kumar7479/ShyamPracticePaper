document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll(".flash-message").forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = "0";
            setTimeout(() => msg.remove(), 500);
        }, 3000);
    });
});
