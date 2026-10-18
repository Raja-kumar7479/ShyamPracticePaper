(function () {
    var exit = document.exitFullscreen || document.webkitExitFullscreen || document.msExitFullscreen;
    if (exit && (document.fullscreenElement || document.webkitFullscreenElement)) {
        try { exit.call(document); } catch (e) {}
    }
})();

const PAGE_DATA = document.getElementById('pageData').dataset;

    document.getElementById('submitFeedbackBtn').addEventListener('click', async () => {
        const submitUrl = PAGE_DATA.submitFeedbackUrl;

        const softwareFeedbackElement = document.querySelector('input[name="software"]:checked');
        const contentFeedbackElement = document.querySelector('input[name="content"]:checked');
        const speedFeedbackElement = document.querySelector('input[name="speed"]:checked');
        const suggestions = document.getElementById('suggestions').value;

        const softwareFeedback = softwareFeedbackElement ? softwareFeedbackElement.value : null;
        const contentFeedback = contentFeedbackElement ? contentFeedbackElement.value : null;
        const speedFeedback = speedFeedbackElement ? speedFeedbackElement.value : null;

        if (!softwareFeedback || !contentFeedback || !speedFeedback) {
            alert('Please provide feedback for all required fields (Software, Content, and Speed).');
            return;
        }

        const feedbackData = {
            software_feedback: softwareFeedback,
            content_feedback: contentFeedback,
            speed_feedback: speedFeedback,
            suggestions: suggestions
        };

        const submitButton = document.getElementById('submitFeedbackBtn');
        submitButton.disabled = true;
        submitButton.textContent = 'Submitting...';

        try {
            const response = await fetch(submitUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(feedbackData)
            });

            const result = await response.json();

            if (response.ok) {
                alert(result.message);
                window.location.replace(result.redirect_url);
            } else {
                alert('Error: ' + (result.message || 'Failed to submit feedback. Please try again.'));
            }
        } catch (error) {
            console.error('Error submitting feedback:', error);
            alert('An unexpected network error occurred. Please check your internet connection.');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = 'Submit Feedback';
        }
    });
