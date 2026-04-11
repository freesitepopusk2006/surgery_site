(function () {
    var widget = document.getElementById("bookingWidget");
    if (!widget) return;

    var fab = document.getElementById("bookingFab");
    var panel = document.getElementById("bookingPanel");
    var backdrop = document.getElementById("bookingBackdrop");
    var closeBtn = document.getElementById("bookingClose");
    var form = document.getElementById("bookingForm");
    var formWrap = document.getElementById("bookingFormWrap");
    var success = document.getElementById("bookingSuccess");
    var successClose = document.getElementById("bookingSuccessClose");

    function resetBooking() {
        if (form) form.reset();
        if (formWrap) formWrap.hidden = false;
        if (success) success.hidden = true;
    }

    function openPanel() {
        if (panel) panel.hidden = false;
        if (backdrop) backdrop.hidden = false;
        if (fab) {
            fab.hidden = true;
            fab.setAttribute("aria-expanded", "true");
        }
        document.body.style.overflow = "hidden";
        if (closeBtn) closeBtn.focus();
    }

    function closePanel() {
        if (panel) panel.hidden = true;
        if (backdrop) backdrop.hidden = true;
        if (fab) {
            fab.hidden = false;
            fab.setAttribute("aria-expanded", "false");
        }
        document.body.style.overflow = "";
        resetBooking();
    }

    if (fab) fab.addEventListener("click", openPanel);
    if (closeBtn) closeBtn.addEventListener("click", closePanel);
    if (backdrop) backdrop.addEventListener("click", closePanel);
    if (successClose) successClose.addEventListener("click", closePanel);

    if (form) {
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }
            if (formWrap) formWrap.hidden = true;
            if (success) success.hidden = false;
        });
    }

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && panel && !panel.hidden) {
            closePanel();
        }
    });
})();
