function finishStep1() {
        if(!document.getElementById('consentCheck').checked) {
            alert("Please accept the terms to proceed.");
            return;
        }
        if (window.sppMarkInternalNav) window.sppMarkInternalNav();
        window.location.href = document.getElementById('cvFinishUrl').value;
    }
