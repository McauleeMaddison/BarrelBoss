(() => {
    const root = document.documentElement;
    const body = document.body;
    const themeStorageKey = "barrelboss-theme";
    const navToggleButtons = document.querySelectorAll("[data-nav-toggle]");
    const closeButton = document.querySelector(".sidebar-close");
    const overlay = document.querySelector(".nav-overlay");
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    const themeToggleButton = document.querySelector("[data-theme-toggle]");
    const themeToggleLabel = document.querySelector("[data-theme-toggle-label]");
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const isMobileNav = window.matchMedia("(max-width: 900px)");
    const prefersDarkScheme = window.matchMedia
        ? window.matchMedia("(prefers-color-scheme: dark)")
        : null;
    let lockedScrollY = 0;

    const getStoredTheme = () => {
        try {
            return window.localStorage.getItem(themeStorageKey);
        } catch (_error) {
            return null;
        }
    };

    const setStoredTheme = (theme) => {
        try {
            window.localStorage.setItem(themeStorageKey, theme);
        } catch (_error) {
            // Ignore storage errors.
        }
    };

    const applyTheme = (theme, { persist = false } = {}) => {
        const normalizedTheme = theme === "dark" ? "dark" : "light";
        root.dataset.theme = normalizedTheme;
        body.dataset.theme = normalizedTheme;
        root.style.colorScheme = normalizedTheme;
        body.classList.toggle("theme-dark", normalizedTheme === "dark");
        body.classList.toggle("theme-light", normalizedTheme === "light");

        if (themeToggleButton) {
            themeToggleButton.setAttribute(
                "aria-pressed",
                String(normalizedTheme === "dark"),
            );
            themeToggleButton.setAttribute(
                "aria-label",
                normalizedTheme === "dark"
                    ? "Switch to light mode"
                    : "Switch to dark mode",
            );
        }

        if (themeToggleLabel) {
            themeToggleLabel.textContent =
                normalizedTheme === "dark" ? "Dark" : "Light";
        }

        if (themeColorMeta) {
            themeColorMeta.setAttribute(
                "content",
                normalizedTheme === "dark" ? "#101927" : "#f4f1ea",
            );
        }

        if (persist) {
            setStoredTheme(normalizedTheme);
        }
    };

    const resolveInitialTheme = () => {
        const stored = getStoredTheme();
        if (stored === "light" || stored === "dark") {
            return stored;
        }
        if (prefersDarkScheme && prefersDarkScheme.matches) {
            return "dark";
        }
        return "light";
    };

    const lockBodyScroll = () => {
        lockedScrollY = window.scrollY || window.pageYOffset || 0;
        body.style.position = "fixed";
        body.style.top = `-${lockedScrollY}px`;
        body.style.left = "0";
        body.style.right = "0";
        body.style.width = "100%";
    };

    const unlockBodyScroll = () => {
        if (!body.style.position) {
            return;
        }

        body.style.position = "";
        body.style.top = "";
        body.style.left = "";
        body.style.right = "";
        body.style.width = "";
        window.scrollTo(0, lockedScrollY);
    };

    const setNavState = (isOpen) => {
        const shouldOpen = isMobileNav.matches ? isOpen : false;
        body.classList.toggle("nav-open", shouldOpen);

        navToggleButtons.forEach((button) => {
            button.setAttribute("aria-expanded", String(shouldOpen));
        });

        if (overlay) {
            overlay.setAttribute("aria-hidden", String(!shouldOpen));
        }

        if (shouldOpen) {
            lockBodyScroll();
        } else {
            unlockBodyScroll();
        }
    };

    const closeNav = () => setNavState(false);

    applyTheme(resolveInitialTheme());

    if (themeToggleButton) {
        themeToggleButton.addEventListener("click", () => {
            const current = root.dataset.theme === "dark" ? "dark" : "light";
            applyTheme(current === "dark" ? "light" : "dark", { persist: true });
        });
    }

    if (prefersDarkScheme && !getStoredTheme()) {
        const handleSchemeChange = (event) => {
            applyTheme(event.matches ? "dark" : "light");
        };

        if (typeof prefersDarkScheme.addEventListener === "function") {
            prefersDarkScheme.addEventListener("change", handleSchemeChange);
        } else if (typeof prefersDarkScheme.addListener === "function") {
            prefersDarkScheme.addListener(handleSchemeChange);
        }
    }

    navToggleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (!isMobileNav.matches) {
                return;
            }
            setNavState(!body.classList.contains("nav-open"));
        });
    });

    if (isMobileNav.matches) {
        closeNav();
    }

    if (closeButton) {
        closeButton.addEventListener("click", closeNav);
    }

    if (overlay) {
        overlay.addEventListener("click", closeNav);
        overlay.addEventListener("touchend", closeNav, { passive: true });
    }

    navLinks.forEach((link) => {
        link.addEventListener("click", closeNav);
    });

    window.addEventListener("resize", () => {
        if (!isMobileNav.matches) {
            closeNav();
        } else if (body.classList.contains("nav-open")) {
            lockBodyScroll();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeNav();
        }
    });

    const passwordToggleButtons = document.querySelectorAll("[data-password-toggle]");
    passwordToggleButtons.forEach((button) => {
        const targetId = button.dataset.passwordTarget;
        if (!targetId) {
            return;
        }

        const passwordInput = document.getElementById(targetId);
        if (!passwordInput) {
            return;
        }

        button.addEventListener("click", () => {
            const isShowing = passwordInput.type === "text";
            passwordInput.type = isShowing ? "password" : "text";
            button.textContent = isShowing ? "Show" : "Hide";
            button.setAttribute("aria-pressed", String(!isShowing));
            button.setAttribute(
                "aria-label",
                isShowing ? "Show password" : "Hide password",
            );
        });
    });
})();
