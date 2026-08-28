document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('sidebarToggle');
    const closeBtn = document.getElementById('sidebarClose');
    const sidebar = document.getElementById('mobileSidebar');
    const overlay = document.getElementById('sidebarOverlay');

    function openSidebar() {
        if(sidebar && overlay) {
            sidebar.classList.add('open');
            overlay.classList.add('show');
            document.body.style.overflow = 'hidden';
            sidebar.setAttribute('aria-hidden', 'false');
            if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
        }
    }

    function closeSidebar() {
        if(sidebar && overlay) {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            document.body.style.overflow = '';
            sidebar.setAttribute('aria-hidden', 'true');
            if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
        }
    }

    if (toggleBtn) toggleBtn.addEventListener('click', () => {
        if (sidebar && sidebar.classList.contains('open')) closeSidebar();
        else openSidebar();
    });
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (overlay) overlay.addEventListener('click', closeSidebar);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('open')) closeSidebar();
    });

    const cookieBanner = document.getElementById('cookieBanner');
    const cookieModalEl = document.getElementById('cookieModal');
    const cookieModal = (cookieModalEl && window.bootstrap) ? new bootstrap.Modal(cookieModalEl) : null;

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    function setConsentCookie(obj) {
        const d = new Date();
        d.setTime(d.getTime() + 365 * 24 * 60 * 60 * 1000);
        document.cookie = `cookie_consent=${encodeURIComponent(JSON.stringify(obj))}; expires=${d.toUTCString()}; path=/; SameSite=Lax`;
    }

    function deleteCookie(name) {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=${location.hostname}`;
    }

    function parseConsentValue(raw) {
        if (!raw) return null;
        let v = raw;
        if (v.charAt(0) === '"' && v.charAt(v.length - 1) === '"') v = v.slice(1, -1);
        try { return JSON.parse(decodeURIComponent(v)); } catch (e) {}
        try { return JSON.parse(v); } catch (e) {}
        return null;
    }

    const NON_ESSENTIAL_COOKIES = {
        analytics: ['_ga', '_gid', '_gat'],
        marketing: ['_fbp', '_gcl_au', 'IDE', 'fr']
    };

    window.CookieConsent = { necessary: true, analytics: false, marketing: false };

    function applyConsent(prefs) {
        window.CookieConsent = {
            necessary: true,
            analytics: !!prefs.analytics,
            marketing: !!prefs.marketing
        };
        if (!window.CookieConsent.analytics) NON_ESSENTIAL_COOKIES.analytics.forEach(deleteCookie);
        if (!window.CookieConsent.marketing) NON_ESSENTIAL_COOKIES.marketing.forEach(deleteCookie);
        const a = document.getElementById('consentAnalytics');
        const m = document.getElementById('consentMarketing');
        if (a) a.checked = window.CookieConsent.analytics;
        if (m) m.checked = window.CookieConsent.marketing;
        document.dispatchEvent(new CustomEvent('cookieconsent:updated', { detail: window.CookieConsent }));
    }

    const consentAttr = document.body.dataset.cookieConsent;
    let dbConsent = null;
    try {
        if (consentAttr && consentAttr !== 'null') dbConsent = JSON.parse(consentAttr);
    } catch (e) {}

    const savedConsent = parseConsentValue(getCookie('cookie_consent'));

    if (savedConsent) {
        applyConsent(savedConsent);
    } else if (dbConsent) {
        applyConsent(dbConsent);
        setConsentCookie(dbConsent);
    } else {
        setTimeout(() => { if (cookieBanner) cookieBanner.classList.add('show'); }, 1000);
    }

    async function saveConsent(preferences) {
        const full = { necessary: true, analytics: !!preferences.analytics, marketing: !!preferences.marketing };
        if (cookieBanner) cookieBanner.classList.remove('show');
        if (cookieModal) cookieModal.hide();
        applyConsent(full);
        setConsentCookie(full);
        try {
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const res = await fetch('/api/cookie-consent', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfMeta ? csrfMeta.getAttribute('content') : ''
                },
                body: JSON.stringify(full)
            });
            const out = await res.json().catch(() => null);
            if (out && out.consent) applyConsent(out.consent);
        } catch (error) {
            console.error('Failed to save consent:', error);
        }
    }

    document.getElementById('cookieAcceptBtn')?.addEventListener('click', () => saveConsent({ analytics: true, marketing: true }));
    document.getElementById('cookieRejectBtn')?.addEventListener('click', () => saveConsent({ analytics: false, marketing: false }));
    document.getElementById('cookieCustomizeBtn')?.addEventListener('click', () => {
        const a = document.getElementById('consentAnalytics');
        const m = document.getElementById('consentMarketing');
        if (a) a.checked = window.CookieConsent.analytics;
        if (m) m.checked = window.CookieConsent.marketing;
        if (cookieBanner) cookieBanner.classList.remove('show');
        if (cookieModal) cookieModal.show();
    });
    document.getElementById('cookieSavePreferencesBtn')?.addEventListener('click', () => {
        const analytics = document.getElementById('consentAnalytics')?.checked || false;
        const marketing = document.getElementById('consentMarketing')?.checked || false;
        saveConsent({ analytics, marketing });
    });
});