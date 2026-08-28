class ProctoringSystem {
    constructor(sectionId, testKey, userEmail, courseCode, uniqueCode) {
        this.sectionId = sectionId;
        this.testKey = testKey;
        this.userEmail = userEmail;
        this.courseCode = courseCode;
        this.uniqueCode = uniqueCode;
        this.isTerminated = false;
        this.violationCount = 0;
        this.initialize();
    }

    initialize() {
        this.detectDevTools();
        this.handleVisibilityChange();
        this.handleFullscreenChange();
        this.disableContextMenu();
        this.disableCopyPaste();
    }

    async sendViolation(violationType, details) {
        if (this.isTerminated) {
            console.warn("Test already terminated. No more violations will be sent.");
            return;
        }

        this.violationCount++;
        console.warn(`Violation detected (${this.violationCount}): ${violationType}`, details);

        try {
            const response = await fetch(`/api/record-violation/${this.testKey}/${this.courseCode}/${this.uniqueCode}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ violationType, details })
            });

            if (response.status === 403) {
                const result = await response.json();
                if (result.status === 'terminated') {
                    this.isTerminated = true;
                    window.sppExamLeaving = true;
                    if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
                    window.location.replace(`/test-terminated/${this.testKey}/${this.courseCode}/${this.uniqueCode}/${violationType}`);
                }
            } else if (!response.ok) {
                console.error(`Server error on sending violation: ${response.status}`);
            }
        } catch (error) {
            console.error('Failed to send violation report:', error);
        }
    }

    detectDevTools() {
        const threshold = 160;
        const checkDevTools = () => {
            if (window.outerWidth - window.innerWidth > threshold || window.outerHeight - window.innerHeight > threshold) {
                this.sendViolation('devtools_open', 'Developer tools were opened.');
            }
        };
        setInterval(checkDevTools, 1000);
    }

    handleVisibilityChange() {
        this.awayLimitSeconds = 20;
        this.awayTimer = null;
        this.awaySince = null;

        document.addEventListener('visibilitychange', () => {
            if (this.isTerminated) return;

            if (document.visibilityState === 'hidden') {
                this.awaySince = Date.now();
                this.awayTimer = setTimeout(() => {
                    this.terminateNow('away_too_long',
                        `Left the assessment window for more than ${this.awayLimitSeconds} seconds.`);
                }, this.awayLimitSeconds * 1000);
            } else {
                if (this.awayTimer) {
                    clearTimeout(this.awayTimer);
                    this.awayTimer = null;
                }
                const awaySec = this.awaySince ? Math.round((Date.now() - this.awaySince) / 1000) : 0;
                this.awaySince = null;
                if (awaySec >= this.awayLimitSeconds) {
                    this.terminateNow('away_too_long',
                        `Left the assessment window for ${awaySec} seconds.`);
                } else {
                    this.sendViolation('tab_switch',
                        `User left the assessment window for ${awaySec} second(s).`);
                }
            }
        });
    }

    async terminateNow(violationType, details) {
        if (this.isTerminated) return;
        this.isTerminated = true;
        if (this.awayTimer) {
            clearTimeout(this.awayTimer);
            this.awayTimer = null;
        }
        try {
            await fetch(`/api/terminate-violation/${this.testKey}/${this.courseCode}/${this.uniqueCode}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ violationType, details })
            });
        } catch (e) {
            console.error('Terminate report failed', e);
        }
        if (window.markTestFinished) window.markTestFinished();
        window.sppExamLeaving = true;
        if (typeof window.sppMarkExamFinished === 'function') window.sppMarkExamFinished();
        window.location.replace(
            `/test-terminated/${this.testKey}/${this.courseCode}/${this.uniqueCode}/${violationType}`);
    }

    handleFullscreenChange() {
        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement) {
                if (window.sppAllowFsExit) {
                    window.sppAllowFsExit = false;
                    return;
                }
                this.sendViolation('fullscreen_exit', 'User exited full-screen mode.');
            }
        });
    }

    disableContextMenu() {
        window.addEventListener('contextmenu', e => {
            e.preventDefault();
            this.sendViolation('context_menu', 'Right-click (context menu) was disabled and attempted.');
        });
    }

    disableCopyPaste() {
        const events = ['copy', 'paste', 'cut'];
        events.forEach(event => {
            window.addEventListener(event, e => {
                e.preventDefault();
                this.sendViolation(`clipboard_${event}`, `Attempted to ${event} content.`);
            });
        });
    }
}