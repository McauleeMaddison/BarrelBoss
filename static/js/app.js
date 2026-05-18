(() => {
    const body = document.body;
    const themeStorageKey = "barrelboss-theme";
    const menuButton = document.querySelector(".menu-btn");
    const closeButton = document.querySelector(".sidebar-close");
    const overlay = document.querySelector(".nav-overlay");
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    const themeToggleButton = document.querySelector("[data-theme-toggle]");
    const themeToggleLabel = document.querySelector("[data-theme-toggle-label]");
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const isMobileNav = window.matchMedia(
        "(max-width: 1180px), (hover: none) and (pointer: coarse) and (max-width: 1366px)",
    );
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
            // Ignore storage errors (for example, private browsing restrictions).
        }
    };

    const applyTheme = (theme, { persist = false } = {}) => {
        const normalizedTheme = theme === "dark" ? "dark" : "light";
        body.dataset.theme = normalizedTheme;
        body.classList.toggle("theme-dark", normalizedTheme === "dark");
        body.classList.toggle("theme-light", normalizedTheme === "light");

        if (themeToggleButton) {
            themeToggleButton.setAttribute(
                "aria-pressed",
                String(normalizedTheme === "dark"),
            );
        }

        if (themeToggleLabel) {
            themeToggleLabel.textContent =
                normalizedTheme === "dark" ? "Dark" : "Light";
        }

        if (themeColorMeta) {
            themeColorMeta.setAttribute(
                "content",
                normalizedTheme === "dark" ? "#101317" : "#f5f6f8",
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

    applyTheme(resolveInitialTheme());

    if (themeToggleButton) {
        themeToggleButton.addEventListener("click", () => {
            const current = body.dataset.theme === "dark" ? "dark" : "light";
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
        body.classList.toggle("nav-open", isOpen);
        if (menuButton) {
            menuButton.setAttribute("aria-expanded", String(isOpen));
        }

        if (overlay) {
            overlay.setAttribute("aria-hidden", String(!isOpen));
        }

        if (isMobileNav.matches) {
            if (isOpen) {
                lockBodyScroll();
            } else {
                unlockBodyScroll();
            }
        } else {
            unlockBodyScroll();
        }
    };
    const openNav = () => setNavState(true);
    const closeNav = () => setNavState(false);
    if (menuButton) {
        menuButton.addEventListener("click", () => {
            if (body.classList.contains("nav-open")) {
                closeNav();
                return;
            }

            openNav();
        });
    }

    if (closeButton) {
        closeButton.addEventListener("click", closeNav);
    }

    if (overlay) {
        overlay.addEventListener("click", closeNav);
        overlay.addEventListener("touchend", closeNav, { passive: true });
    }

    if (navLinks.length) {
        navLinks.forEach((link) => {
            link.addEventListener("click", closeNav);
        });
    }

    window.addEventListener("resize", closeNav);

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeNav();
        }
    });

    const passwordToggleButtons = document.querySelectorAll("[data-password-toggle]");
    if (passwordToggleButtons.length) {
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
    }

    const dashboardPanelButtons = document.querySelectorAll("[data-dashboard-panel-target]");
    const dashboardPanelGroups = document.querySelectorAll("[data-dashboard-panel-group]");
    const dashboardPanelSelect = document.querySelector("[data-dashboard-panel-select]");
    if (dashboardPanelButtons.length && dashboardPanelGroups.length) {
        const setDashboardPanel = (target) => {
            dashboardPanelGroups.forEach((group) => {
                const isMatch = group.dataset.dashboardPanelGroup === target;
                group.hidden = !isMatch;
            });

            dashboardPanelButtons.forEach((button) => {
                const isActive = button.dataset.dashboardPanelTarget === target;
                button.classList.toggle("active", isActive);
            });

            if (dashboardPanelSelect && dashboardPanelSelect.value !== target) {
                dashboardPanelSelect.value = target;
            }
        };

        dashboardPanelButtons.forEach((button) => {
            button.addEventListener("click", () => {
                setDashboardPanel(button.dataset.dashboardPanelTarget);
            });
        });

        if (dashboardPanelSelect) {
            dashboardPanelSelect.addEventListener("change", () => {
                setDashboardPanel(dashboardPanelSelect.value);
            });
        }

        const defaultTarget = dashboardPanelSelect?.value || dashboardPanelButtons[0].dataset.dashboardPanelTarget;
        setDashboardPanel(defaultTarget);
    }

    const activityButtons = document.querySelectorAll("[data-activity-filter]");
    const activityRows = document.querySelectorAll("#activityList [data-activity-category]");

    if (activityButtons.length && activityRows.length) {
        activityButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const filter = button.dataset.activityFilter;

                activityButtons.forEach((btn) => btn.classList.remove("active"));
                button.classList.add("active");

                activityRows.forEach((row) => {
                    const category = row.dataset.activityCategory;
                    row.hidden = !(filter === "all" || filter === category);
                });
            });
        });
    }

    const throughputButtons = document.querySelectorAll("[data-throughput-mode]");
    const throughputBars = document.querySelectorAll(".throughput-bar[data-service]");
    const throughputValues = document.querySelectorAll(".throughput-value[data-service]");

    if (throughputButtons.length && throughputBars.length) {
        throughputButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const mode = button.dataset.throughputMode;

                throughputButtons.forEach((btn) => btn.classList.remove("active"));
                button.classList.add("active");

                throughputBars.forEach((bar) => {
                    const value = bar.dataset[mode] || bar.dataset.service || "0";
                    bar.style.height = `${value}%`;
                });

                throughputValues.forEach((valueNode) => {
                    const value = valueNode.dataset[mode] || valueNode.dataset.service || "0";
                    valueNode.textContent = `${value}%`;
                });
            });
        });
    }

    const shiftChartBars = document.querySelectorAll(".shift-chart-bar[data-shift-day]");
    const shiftChartDay = document.getElementById("shiftChartDay");
    const shiftChartHours = document.getElementById("shiftChartHours");
    const shiftChartDate = document.getElementById("shiftChartDate");

    if (shiftChartBars.length && shiftChartDay && shiftChartHours && shiftChartDate) {
        const setShiftFocus = (bar) => {
            shiftChartDay.textContent = bar.dataset.shiftDay || "-";
            shiftChartHours.textContent = bar.dataset.shiftHours || "0h";
            shiftChartDate.textContent = bar.dataset.shiftDate || "No shifts this week";

            shiftChartBars.forEach((item) => item.classList.remove("active"));
            bar.classList.add("active");
        };

        let hasActiveBar = false;
        shiftChartBars.forEach((bar) => {
            if (bar.classList.contains("active")) {
                hasActiveBar = true;
            }

            bar.addEventListener("click", () => setShiftFocus(bar));
            bar.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setShiftFocus(bar);
                }
            });
        });

        if (!hasActiveBar) {
            setShiftFocus(shiftChartBars[0]);
        }
    }

    const tableSortExtractValue = (cell) => {
        const raw = (cell?.dataset?.sortValue || cell?.textContent || "").replace(/\s+/g, " ").trim();

        if (!raw || raw === "-" || raw === "—") {
            return { kind: "empty", value: "" };
        }

        const maybeDate = Date.parse(raw);
        if (!Number.isNaN(maybeDate) && (raw.includes("-") || raw.includes("/") || /[A-Za-z]{3,}/.test(raw))) {
            return { kind: "number", value: maybeDate };
        }

        const numericCandidate = raw
            .replace(/,/g, "")
            .replace(/[£$€%]/g, "")
            .replace(/mins?/gi, "")
            .replace(/h$/i, "")
            .trim();

        if (/^-?\d+(\.\d+)?$/.test(numericCandidate)) {
            return { kind: "number", value: Number.parseFloat(numericCandidate) };
        }

        return { kind: "text", value: raw.toLowerCase() };
    };

    const setupDataTables = () => {
        const dataTables = document.querySelectorAll("table.data-table");
        if (!dataTables.length) {
            return;
        }

        dataTables.forEach((table) => {
            const headers = Array.from(table.querySelectorAll("thead th"));
            const bodySection = table.tBodies && table.tBodies.length ? table.tBodies[0] : null;
            if (!headers.length || !bodySection) {
                return;
            }

            Array.from(bodySection.rows).forEach((row) => {
                Array.from(row.cells).forEach((cell, columnIndex) => {
                    const headerCell = headers[columnIndex];
                    const headerLabel = headerCell
                        ? headerCell.textContent.replace(/\s+/g, " ").trim()
                        : `Column ${columnIndex + 1}`;
                    cell.setAttribute("data-label", headerLabel || `Column ${columnIndex + 1}`);
                });
            });

            if (!table.classList.contains("js-sortable")) {
                return;
            }

            headers.forEach((header, columnIndex) => {
                const heading = header.textContent.replace(/\s+/g, " ").trim().toLowerCase();
                const sortDisabled = header.dataset.sort === "off" || heading.includes("action") || heading === "toggle";
                if (sortDisabled) {
                    return;
                }

                const hasCells = Array.from(bodySection.rows).some((row) => row.cells[columnIndex]);
                if (!hasCells) {
                    return;
                }

                header.classList.add("is-sortable");
                header.tabIndex = 0;
                header.setAttribute("role", "button");
                header.setAttribute("aria-sort", "none");

                const sortColumn = () => {
                    const nextDirection = header.dataset.sortDirection === "asc" ? "desc" : "asc";
                    const directionFactor = nextDirection === "asc" ? 1 : -1;

                    headers.forEach((item) => {
                        item.removeAttribute("data-sort-direction");
                        if (item.classList.contains("is-sortable")) {
                            item.setAttribute("aria-sort", "none");
                        }
                    });

                    header.dataset.sortDirection = nextDirection;
                    header.setAttribute("aria-sort", nextDirection === "asc" ? "ascending" : "descending");

                    const indexedRows = Array.from(bodySection.rows).map((row, rowIndex) => ({
                        row,
                        rowIndex,
                        sortValue: tableSortExtractValue(row.cells[columnIndex]),
                    }));

                    indexedRows.sort((left, right) => {
                        const leftEmpty = left.sortValue.kind === "empty";
                        const rightEmpty = right.sortValue.kind === "empty";
                        if (leftEmpty || rightEmpty) {
                            if (leftEmpty && rightEmpty) {
                                return left.rowIndex - right.rowIndex;
                            }
                            return leftEmpty ? 1 : -1;
                        }

                        if (left.sortValue.kind === "number" && right.sortValue.kind === "number") {
                            const numericDiff = left.sortValue.value - right.sortValue.value;
                            return numericDiff === 0
                                ? left.rowIndex - right.rowIndex
                                : numericDiff * directionFactor;
                        }

                        const textDiff = String(left.sortValue.value).localeCompare(
                            String(right.sortValue.value),
                            undefined,
                            { numeric: true, sensitivity: "base" },
                        );

                        if (textDiff === 0) {
                            return left.rowIndex - right.rowIndex;
                        }

                        return textDiff * directionFactor;
                    });

                    indexedRows.forEach(({ row }) => {
                        bodySection.appendChild(row);
                    });
                };

                header.addEventListener("click", sortColumn);
                header.addEventListener("keydown", (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        sortColumn();
                    }
                });
            });
        });
    };

    setupDataTables();

    const pushSettingsNode = document.querySelector("[data-push-settings]");
    const pushStatus = document.getElementById("pushStatus");

    if (pushSettingsNode && pushStatus) {
        const enableButton = pushSettingsNode.querySelector("[data-push-enable]");
        const disableButton = pushSettingsNode.querySelector("[data-push-disable]");
        const vapidPublicKey = pushSettingsNode.dataset.vapidPublicKey || "";
        const subscribeUrl = pushSettingsNode.dataset.subscribeUrl || "";
        const unsubscribeUrl = pushSettingsNode.dataset.unsubscribeUrl || "";
        const pushConfigured = pushSettingsNode.dataset.configured === "true";
        const initialEnabled = pushSettingsNode.dataset.initialEnabled === "true";

        const setButtons = (enabled) => {
            if (!enableButton || !disableButton) {
                return;
            }

            enableButton.hidden = enabled;
            disableButton.hidden = !enabled;
            enableButton.disabled = false;
            disableButton.disabled = false;
        };

        const getCsrfToken = () => {
            const tokenCookie = document.cookie
                .split(";")
                .map((entry) => entry.trim())
                .find((entry) => entry.startsWith("csrftoken="));
            return tokenCookie ? decodeURIComponent(tokenCookie.split("=")[1]) : "";
        };

        const toUint8Array = (base64String) => {
            const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
            const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
            const rawData = window.atob(base64);
            return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
        };

        const getActiveSubscription = async () => {
            const registration = await navigator.serviceWorker.ready;
            return registration.pushManager.getSubscription();
        };

        const postJson = async (url, payload) => {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                let errorMessage = "Request failed.";
                try {
                    const responsePayload = await response.json();
                    errorMessage = responsePayload.error || errorMessage;
                } catch (_error) {
                    // Fallback to default error message.
                }
                throw new Error(errorMessage);
            }

            return response.json();
        };

        if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
            pushStatus.textContent = "Push alerts are not supported in this browser.";
            if (enableButton) {
                enableButton.disabled = true;
            }
            if (disableButton) {
                disableButton.disabled = true;
            }
            return;
        }

        if (!pushConfigured || !vapidPublicKey) {
            pushStatus.textContent =
                "Push alerts are not configured yet. Add VAPID keys on the server first.";
            if (enableButton) {
                enableButton.disabled = true;
            }
            if (disableButton) {
                disableButton.disabled = true;
            }
            return;
        }

        const syncSubscriptionState = async () => {
            try {
                const subscription = await getActiveSubscription();
                const hasSubscription = Boolean(subscription);
                setButtons(hasSubscription || initialEnabled);
            } catch (_error) {
                setButtons(initialEnabled);
            }
        };

        setButtons(initialEnabled);
        syncSubscriptionState();

        if (enableButton) {
            enableButton.addEventListener("click", async () => {
                enableButton.disabled = true;
                pushStatus.textContent = "Enabling shift alerts...";

                try {
                    const permission = await Notification.requestPermission();
                    if (permission !== "granted") {
                        pushStatus.textContent =
                            "Notification permission was not granted. Alerts remain disabled.";
                        enableButton.disabled = false;
                        return;
                    }

                    const registration = await navigator.serviceWorker.ready;
                    const subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: toUint8Array(vapidPublicKey),
                    });

                    await postJson(subscribeUrl, { subscription: subscription.toJSON() });
                    setButtons(true);
                    pushStatus.textContent = "Shift alerts are active on this device.";
                } catch (error) {
                    pushStatus.textContent = `Could not enable alerts: ${error.message}`;
                    setButtons(false);
                }
            });
        }

        if (disableButton) {
            disableButton.addEventListener("click", async () => {
                disableButton.disabled = true;
                pushStatus.textContent = "Disabling shift alerts...";

                try {
                    const subscription = await getActiveSubscription();
                    const endpoint = subscription ? subscription.endpoint : null;
                    if (subscription) {
                        await subscription.unsubscribe();
                    }

                    await postJson(unsubscribeUrl, { endpoint });
                    setButtons(false);
                    pushStatus.textContent = "Shift alerts are disabled on this device.";
                } catch (error) {
                    pushStatus.textContent = `Could not disable alerts: ${error.message}`;
                    setButtons(true);
                }
            });
        }
    }
})();
