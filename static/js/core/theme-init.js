(() => {
    const root = document.documentElement;
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const themeStorageKey = "barrelboss-theme";
    const prefersDark = window.matchMedia
        && window.matchMedia("(prefers-color-scheme: dark)").matches;
    let theme = prefersDark ? "dark" : "light";

    try {
        const stored = window.localStorage.getItem(themeStorageKey);
        if (stored === "dark" || stored === "light") {
            theme = stored;
        }
    } catch (_error) {
        // Ignore storage errors during initial paint.
    }

    root.dataset.theme = theme;
    root.style.colorScheme = theme;

    if (themeColorMeta) {
        themeColorMeta.setAttribute(
            "content",
            theme === "dark" ? "#101927" : "#f4f1ea",
        );
    }
})();
