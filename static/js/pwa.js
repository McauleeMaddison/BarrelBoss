(() => {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch(() => {
            // Keep install flow non-blocking if service worker registration fails.
        });
    });
})();
