(() => {
    const root = document.documentElement;
    const body = document.body;
    const themeStorageKey = "barrelboss-theme";
    const navToggleButtons = document.querySelectorAll("[data-nav-toggle]");
    const commandToggleButtons = document.querySelectorAll("[data-command-toggle]");
    const commandCloseButtons = document.querySelectorAll("[data-command-close]");
    const closeButton = document.querySelector(".sidebar-close");
    const overlay = document.querySelector(".nav-overlay");
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    const commandLinks = document.querySelectorAll(".mobile-command-link");
    const commandBackdrop = document.querySelector(".command-sheet-backdrop");
    const commandSheet = document.querySelector(".mobile-command-sheet");
    const themeToggleButton = document.querySelector("[data-theme-toggle]");
    const themeToggleLabel = document.querySelector("[data-theme-toggle-label]");
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const isOverlayNav = window.matchMedia("(max-width: 1180px)");
    const isCompactDock = window.matchMedia("(max-width: 1180px)");
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
        if (body.style.position === "fixed") {
            return;
        }
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

    const syncBodyScrollLock = () => {
        if (
            body.classList.contains("nav-open")
            || body.classList.contains("command-open")
        ) {
            lockBodyScroll();
            return;
        }

        unlockBodyScroll();
    };

    const updateExpandedState = (buttons, isExpanded) => {
        buttons.forEach((button) => {
            button.setAttribute("aria-expanded", String(isExpanded));
        });
    };

    const setCommandState = (isOpen) => {
        const shouldOpen = isCompactDock.matches ? isOpen : false;
        body.classList.toggle("command-open", shouldOpen);
        updateExpandedState(commandToggleButtons, shouldOpen);

        if (commandSheet) {
            commandSheet.setAttribute("aria-hidden", String(!shouldOpen));
        }

        if (commandBackdrop) {
            commandBackdrop.setAttribute("aria-hidden", String(!shouldOpen));
        }

        syncBodyScrollLock();
    };

    const setNavState = (isOpen) => {
        const shouldOpen = isOverlayNav.matches ? isOpen : false;
        body.classList.toggle("nav-open", shouldOpen);
        updateExpandedState(navToggleButtons, shouldOpen);

        if (overlay) {
            overlay.setAttribute("aria-hidden", String(!shouldOpen));
        }

        if (shouldOpen && body.classList.contains("command-open")) {
            setCommandState(false);
        }

        syncBodyScrollLock();
    };

    const closeNav = () => setNavState(false);
    const closeCommandSheet = () => setCommandState(false);

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
            if (!isOverlayNav.matches) {
                return;
            }
            setNavState(!body.classList.contains("nav-open"));
        });
    });

    commandToggleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (!isCompactDock.matches) {
                return;
            }
            if (body.classList.contains("nav-open")) {
                setNavState(false);
            }
            setCommandState(!body.classList.contains("command-open"));
        });
    });

    if (isOverlayNav.matches) {
        closeNav();
    }
    if (isCompactDock.matches) {
        closeCommandSheet();
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

    commandCloseButtons.forEach((button) => {
        button.addEventListener("click", closeCommandSheet);
    });

    if (commandBackdrop) {
        commandBackdrop.addEventListener("touchend", closeCommandSheet, { passive: true });
    }

    commandLinks.forEach((link) => {
        link.addEventListener("click", closeCommandSheet);
    });

    window.addEventListener("resize", () => {
        if (!isOverlayNav.matches) {
            closeNav();
        }
        if (!isCompactDock.matches) {
            closeCommandSheet();
        }
        syncBodyScrollLock();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            if (body.classList.contains("command-open")) {
                closeCommandSheet();
                return;
            }
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
