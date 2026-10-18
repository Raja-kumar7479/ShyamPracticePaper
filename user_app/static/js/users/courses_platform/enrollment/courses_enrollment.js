document.addEventListener('DOMContentLoaded', () => {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

    const guestPopup          = document.getElementById('guestCoursePopup');
    const guestGroupGrid      = document.getElementById('guestGroupGrid');
    const guestCourseGrid     = document.getElementById('guestCourseGridContainer');
    const popupSpinner        = document.getElementById('popupLoadingSpinner');
    const popupTitle          = document.getElementById('popupTitle');
    const popupBackBtn        = document.getElementById('popupBackBtn');
    const enrollPopup         = document.getElementById('enrollment-popup');
    const limitPopup          = document.getElementById('enrollment-limit-popup');
    const enrollForm          = document.getElementById('enroll-form');

    let currentCourseCode  = null;
    let currentCourseName  = null;
    let isSubmitting       = false;
    let popupNav           = { group: null, subgroup: null };

    window.popupGoBack = () => {
        if (popupNav.subgroup) {
            loadCoursesForGroup(popupNav.group);
        } else {
            popupNav = { group: null, subgroup: null };
            resetPopupToGroups();
        }
    };

    window.showGuestCoursePopup = (e) => {
        if (e) e.preventDefault();
        openPopup(guestPopup);
        resetPopupToGroups();
        document.body.classList.add('popup-active');
    };

    window.closeGuestCoursePopup = () => {
        closePopup(guestPopup);
        document.body.classList.remove('popup-active');
    };

    window.resetPopupToGroups = () => {
        if (guestGroupGrid)  guestGroupGrid.style.display  = 'grid';
        if (guestCourseGrid) guestCourseGrid.style.display = 'none';
        if (popupSpinner)    popupSpinner.style.display    = 'none';
        if (popupTitle)      popupTitle.textContent        = 'Choose Your Path';
        if (popupBackBtn)    popupBackBtn.style.display    = 'none';
        if (guestCourseGrid) guestCourseGrid.innerHTML     = '';
    };

    if (guestGroupGrid) {
        guestGroupGrid.querySelectorAll('.guest-course-card').forEach(card => {
            card.addEventListener('click', () => loadCoursesForGroup(card.getAttribute('data-group-name')));
        });
    }

    async function loadCoursesForGroup(groupName) {
        popupNav = { group: groupName, subgroup: null };
        guestGroupGrid.style.display  = 'none';
        popupSpinner.style.display    = 'flex';
        popupTitle.textContent        = groupName;
        popupBackBtn.style.display    = 'block';

        try {
            const res  = await fetch(`/api/courses/by-group/${encodeURIComponent(groupName)}`);
            const data = await res.json();

            popupSpinner.style.display    = 'none';
            guestCourseGrid.style.display = 'grid';
            guestCourseGrid.innerHTML     = '';

            const subgroups = data.subgroups || [];
            const courses   = data.courses || [];

            if (data.success && (subgroups.length > 0 || courses.length > 0)) {
                subgroups.forEach(sg => {
                    guestCourseGrid.appendChild(buildSubgroupCard(groupName, sg));
                });
                courses.forEach(course => {
                    guestCourseGrid.appendChild(buildCourseCard(course, data.is_authenticated));
                });
            } else if (data.success) {
                guestCourseGrid.innerHTML = popupEmptyState('fa-box-open', 'No courses available in this group yet.');
            } else {
                showFlash(data.error || 'Could not load courses. Please try again.', 'error');
                renderPopupError(() => loadCoursesForGroup(groupName));
            }
        } catch (err) {
            console.error('loadCoursesForGroup error:', err);
            popupSpinner.style.display = 'none';
            guestCourseGrid.style.display = 'grid';
            showFlash('Network error - could not load courses. Check your connection and try again.', 'error');
            renderPopupError(() => loadCoursesForGroup(groupName));
        }
    }

    async function loadCoursesForSubgroup(groupName, subgroup) {
        popupNav = { group: groupName, subgroup: subgroup };
        guestGroupGrid.style.display  = 'none';
        popupSpinner.style.display    = 'flex';
        popupTitle.textContent        = `${groupName} · ${subgroup}`;
        popupBackBtn.style.display    = 'block';

        try {
            const res  = await fetch(`/api/courses/by-subgroup/${encodeURIComponent(groupName)}/${encodeURIComponent(subgroup)}`);
            const data = await res.json();

            popupSpinner.style.display    = 'none';
            guestCourseGrid.style.display = 'grid';
            guestCourseGrid.innerHTML     = '';

            if (data.success && (data.courses || []).length > 0) {
                data.courses.forEach(course => {
                    guestCourseGrid.appendChild(buildCourseCard(course, data.is_authenticated));
                });
            } else if (data.success) {
                guestCourseGrid.innerHTML = popupEmptyState('fa-box-open', 'No courses available in this subgroup yet.');
            } else {
                showFlash(data.error || 'Could not load courses. Please try again.', 'error');
                renderPopupError(() => loadCoursesForSubgroup(groupName, subgroup));
            }
        } catch (err) {
            console.error('loadCoursesForSubgroup error:', err);
            popupSpinner.style.display = 'none';
            guestCourseGrid.style.display = 'grid';
            showFlash('Network error - could not load courses. Check your connection and try again.', 'error');
            renderPopupError(() => loadCoursesForSubgroup(groupName, subgroup));
        }
    }

    function popupEmptyState(icon, message) {
        return `<div class="popup-empty"><i class="fas ${icon}"></i><p>${escapeHtml(message)}</p></div>`;
    }

    function renderPopupError(retryFn) {
        guestCourseGrid.innerHTML = `<div class="popup-empty popup-empty-error">
            <i class="fas fa-triangle-exclamation"></i>
            <p>Something went wrong while loading.</p>
            <button class="btn btn-open popup-retry-btn" type="button">Try again</button>
        </div>`;
        const btn = guestCourseGrid.querySelector('.popup-retry-btn');
        if (btn && typeof retryFn === 'function') btn.addEventListener('click', retryFn);
    }

    function buildSubgroupCard(groupName, sg) {
        const name  = (typeof sg === 'string') ? sg : sg.subgroup;
        const count = (typeof sg === 'string') ? null : sg.course_count;
        const countText = count === null ? 'Browse courses'
            : `${count} course${count === 1 ? '' : 's'} available`;

        const div = document.createElement('div');
        div.className = 'course-box-card subgroup-card';
        div.style.cursor = 'pointer';
        div.innerHTML = `
            <div class="course-card-header">
                <h4><i class="fas fa-layer-group me-1"></i> ${escapeHtml(name)}</h4>
                <span class="subgroup-count">${escapeHtml(String(countText))}</span>
            </div>
            <p class="course-card-desc">Open <strong>${escapeHtml(name)}</strong> to see its courses and details.</p>
            <button class="btn btn-open w-100"><i class="fas fa-arrow-right me-1"></i> View courses</button>
        `;
        div.addEventListener('click', () => loadCoursesForSubgroup(groupName, name));
        return div;
    }

    function buildCourseCard(course, isAuthenticated) {
        const div = document.createElement('div');
        div.className = 'course-box-card';
        div.setAttribute('data-course-code', course.code);

        let badgeHtml = '';
        if (course.is_enrolled) {
            badgeHtml = `<span class="badge-enrolled"><i class="fas fa-circle-check"></i> Enrolled</span>`;
            div.classList.add('is-enrolled');
        } else if (isAuthenticated && course.is_purchased_content) {
            badgeHtml = `<span class="badge-purchased"><i class="fas fa-check-circle"></i> Purchased</span>`;
        }

        let actionHtml = '';
        if (course.is_enrolled) {
            actionHtml = `
                <button class="btn btn-enrolled w-100" onclick="window.location.href='/courses/${encodeURIComponent(course.code)}/${encodeURIComponent(course.unique_code)}'">
                    <i class="fas fa-door-open me-1"></i> Open
                </button>`;
        } else if (isAuthenticated) {
            actionHtml = `
                <button class="btn btn-open w-100" onclick="handleEnrollment('${course.code}', '${escapeAttr(course.name)}')">
                    <i class="fas fa-graduation-cap me-1"></i> Enroll Now
                </button>
                <p class="course-card-hint"><i class="fas fa-shield-halved"></i> Quick verification, then instant access</p>`;
        } else {
            actionHtml = `
                <button class="btn btn-preview w-100" onclick="exploreCoursePreview('${course.code}')">
                    <i class="fas fa-door-open me-1"></i> Preview Course
                </button>
                <p class="course-card-hint"><i class="fas fa-right-to-bracket"></i> Log in to enroll and save progress</p>`;
        }

        const subLabel = course.subgroup
            ? `<span class="course-card-sub">${escapeHtml(course.subgroup)}</span>` : '';

        div.innerHTML = `
            <div class="course-card-header">
                <h4>${escapeHtml(course.code)}</h4>
                ${badgeHtml}
            </div>
            ${subLabel}
            <div class="course-card-desc rich-desc">${course.description || 'Comprehensive study material for this course.'}</div>
            ${actionHtml}
        `;
        return div;
    }

    function escapeHtml(str) {
        const d = document.createElement('div');
        d.appendChild(document.createTextNode(str || ''));
        return d.innerHTML;
    }

    function escapeAttr(str) {
        return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }

    function markCardEnrolled(code, openUrl) {
        if (!code) return false;
        let updated = false;
        const sel = (window.CSS && CSS.escape) ? CSS.escape(code) : code;
        document.querySelectorAll(`[data-course-code="${sel}"]`).forEach(card => {
            card.classList.add('is-enrolled');

            if (card.classList.contains('br-card-course')) {
                const top = card.querySelector('.br-course-top');
                if (top) {
                    const paid = top.querySelector('.br-badge-paid');
                    if (paid) paid.remove();
                    if (!top.querySelector('.br-badge-enrolled')) {
                        const b = document.createElement('span');
                        b.className = 'br-badge-enrolled';
                        b.innerHTML = '<i class="fas fa-circle-check"></i> Enrolled';
                        top.appendChild(b);
                    }
                }
                const actions = card.querySelector('.br-actions');
                if (actions && openUrl) {
                    actions.innerHTML =
                        `<a class="br-btn br-btn-enrolled" href="${openUrl}"><i class="fas fa-door-open"></i> Open</a>`;
                }
                updated = true;
            } else {
                const badge = card.querySelector('.badge-purchased');
                if (badge) {
                    badge.className = 'badge-enrolled';
                    badge.innerHTML = '<i class="fas fa-circle-check"></i> Enrolled';
                } else {
                    const header = card.querySelector('.course-card-header');
                    if (header && !header.querySelector('.badge-enrolled')) {
                        const b = document.createElement('span');
                        b.className = 'badge-enrolled';
                        b.innerHTML = '<i class="fas fa-circle-check"></i> Enrolled';
                        header.appendChild(b);
                    }
                }
                const btn = card.querySelector('.btn-open, .btn-preview');
                if (btn && openUrl) {
                    btn.className = 'btn btn-enrolled w-100';
                    btn.innerHTML = '<i class="fas fa-door-open me-1"></i> Open';
                    btn.setAttribute('onclick', `window.location.href='${openUrl}'`);
                }
                const hint = card.querySelector('.course-card-hint');
                if (hint) hint.remove();
                updated = true;
            }
        });
        return updated;
    }

    window.exploreCoursePreview = async (courseCode) => {
        try {
            const res  = await fetch('/api/courses/explore-preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ course_code: courseCode })
            });
            const data = await res.json();
            if (data.status === 'success') {
                window.location.href = data.redirect_url;
            } else {
                showFlash(data.message || 'Preview unavailable for this course.', 'error');
            }
        } catch (err) {
            console.error('exploreCoursePreview error:', err);
            showFlash('Network error. Please try again.', 'error');
        }
    };

    window.handleEnrollment = async (code, name) => {
        currentCourseCode = code;
        currentCourseName = name;

        try {
            const res  = await fetch(`/api/enrollment/check?course_code=${encodeURIComponent(code)}`);
            const data = await res.json();

            if (res.status === 401 || res.status === 403) {
                showFlash('Please log in to enroll in a course.', 'error');
                return;
            }

            if (data.status === 'already_enrolled') {
                const codeRes  = await fetch(`/api/courses/get-code?course_code=${encodeURIComponent(code)}`);
                const codeData = await codeRes.json();
                if (codeData.status === 'success') {
                    window.location.href = codeData.redirect_url;
                } else {
                    showFlash('Could not retrieve your course access link.', 'error');
                }
                return;
            }

            if (data.status === 'limit_reached') {
                const msg = document.getElementById('enrollment-limit-message');
                if (msg) msg.textContent = `You have reached the maximum limit of ${data.limit} course enrollments.`;
                openPopup(limitPopup);
                return;
            }

            if (data.status === 'continue') {
                openCaptchaPopup(code, name, false, data.message);
            }
        } catch (err) {
            console.error('handleEnrollment error:', err);
            showFlash('Something went wrong. Please check your connection.', 'error');
        }
    };

    async function openCaptchaPopup(code, name, isPaid, infoMsg) {
        const codeField    = document.getElementById('final-course-code');
        const nameField    = document.getElementById('final-course-name');
        const captchaInput = document.querySelector('#enroll-form input[name="captcha"]');
        const captchaLabel = document.getElementById('captcha-label');
        const captchaError = document.getElementById('captcha-error');
        const submitBtn    = document.querySelector('#enroll-form button[type="submit"]');
        const enrollInfo   = document.getElementById('enroll-info-msg');

        if (codeField)    codeField.value    = code;
        if (nameField)    nameField.value    = name;
        if (captchaInput) captchaInput.value = '';
        if (captchaError) captchaError.textContent = '';

        if (enrollInfo) {
            if (infoMsg) {
                enrollInfo.textContent = infoMsg;
                enrollInfo.style.display = 'block';
            } else {
                enrollInfo.textContent = '';
                enrollInfo.style.display = 'none';
            }
        }

        if (submitBtn) {
            submitBtn.disabled    = true;
            submitBtn.textContent = 'Loading CAPTCHA...';
        }

        openPopup(enrollPopup);

        try {
            const res  = await fetch('/api/enrollment/start');
            const data = await res.json();

            if (data.captcha && captchaLabel) {
                captchaLabel.textContent = `Enter this code: ${data.captcha}`;
                if (captchaInput) {
                    captchaInput.setAttribute('maxlength', String(data.captcha.length));
                    captchaInput.setAttribute('autocomplete', 'off');
                    captchaInput.setAttribute('autocapitalize', 'characters');
                    captchaInput.focus();
                }
                if (submitBtn) {
                    submitBtn.disabled    = false;
                    submitBtn.textContent = isPaid ? 'Verify & Proceed to Pay' : 'Verify & Enroll Free';
                }
            } else {
                if (captchaError) captchaError.textContent = 'Failed to load security check. Please close and try again.';
            }
        } catch (err) {
            console.error('CAPTCHA fetch error:', err);
            if (captchaError) captchaError.textContent = 'Network error loading CAPTCHA. Please close and try again.';
        }
    }

    if (enrollForm) {
        const captchaField = enrollForm.querySelector('input[name="captcha"]');
        if (captchaField) {
            captchaField.addEventListener('input', () => {
                const pos = captchaField.selectionStart;
                captchaField.value = captchaField.value.toUpperCase();
                captchaField.setSelectionRange(pos, pos);
            });
        }
        enrollForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (isSubmitting) return;
            isSubmitting = true;

            const submitBtn   = enrollForm.querySelector('button[type="submit"]');
            const captchaError = document.getElementById('captcha-error');
            const origText    = submitBtn ? submitBtn.textContent : '';

            if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Processing...'; }
            if (captchaError) captchaError.textContent = '';

            const formData = new FormData(enrollForm);

            try {
                const res    = await fetch('/api/enrollment/complete/pre-check', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken },
                    body: formData
                });
                const result = await res.json();

                if (result.success) {
                    closePopup(enrollPopup);
                    markCardEnrolled(currentCourseCode, result.redirect_url);
                    window.location.href = result.redirect_url;
                } else {
                    if (captchaError) captchaError.textContent = result.error || 'Verification failed.';
                    if (result.new_captcha) {
                        const label = document.getElementById('captcha-label');
                        if (label) label.textContent = `Enter this code: ${result.new_captcha}`;
                        const inp = document.querySelector('#enroll-form input[name="captcha"]');
                        if (inp) { inp.value = ''; inp.setAttribute('maxlength', String(result.new_captcha.length)); inp.focus(); }
                    }
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = origText; }
                }
            } catch (err) {
                console.error('Enrollment submit error:', err);
                if (captchaError) captchaError.textContent = 'Network error. Please try again.';
                if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = origText; }
            } finally {
                isSubmitting = false;
            }
        });
    }

    function showFlash(message, type) {
        const container = document.getElementById('popupFlashContainer');
        if (!container) { alert(message); return; }
        container.innerHTML = `
            <div class="popup-flash popup-flash-${type}">
                <i class="fas ${type === 'error' ? 'fa-exclamation-circle' : 'fa-check-circle'} me-2"></i>
                ${escapeHtml(message)}
            </div>`;
        setTimeout(() => { container.innerHTML = ''; }, 5000);
    }

    window.openPopup = (el) => {
        const target = typeof el === 'string' ? document.getElementById(el) : el;
        if (!target) return;
        target.style.display = 'flex';
        requestAnimationFrame(() => target.classList.add('show'));
    };

    window.closePopup = (el) => {
        const target = typeof el === 'string' ? document.getElementById(el) : el;
        if (!target) return;
        target.classList.remove('show');
        setTimeout(() => { target.style.display = 'none'; }, 300);
    };

    // Refresh button: fetch a brand-new CAPTCHA on demand. /api/enrollment/start
    // already pops the old value and mints a fresh one server-side, so this is
    // just a re-fetch that also clears whatever the user had typed.
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('#captcha-refresh');
        if (!btn) return;
        e.preventDefault();
        const label = document.getElementById('captcha-label');
        const input = document.querySelector('#enroll-form input[name="captcha"]');
        const error = document.getElementById('captcha-error');
        const icon  = btn.querySelector('i');
        if (icon) icon.classList.add('fa-spin');
        if (error) error.textContent = '';
        if (input) input.value = '';
        try {
            const res  = await fetch('/api/enrollment/start');
            const data = await res.json();
            if (data.captcha && label) {
                label.textContent = `Enter this code: ${data.captcha}`;
                if (input) {
                    input.setAttribute('maxlength', String(data.captcha.length));
                    input.focus();
                }
            } else if (error) {
                error.textContent = data.error || 'Could not refresh the code.';
            }
        } catch (_) {
            if (error) error.textContent = 'Network error. Please try again.';
        } finally {
            if (icon) icon.classList.remove('fa-spin');
        }
    });
});