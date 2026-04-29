(() => {
    const body = document.body;
    const menuButton = document.querySelector(".menu-btn");
    const closeButton = document.querySelector(".sidebar-close");
    const overlay = document.querySelector(".nav-overlay");
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    const desktopNavToggle = document.querySelector("[data-desktop-nav-toggle]");
    const navCollapseQuery =
        "(max-width: 1180px), (hover: none) and (pointer: coarse) and (max-width: 1366px)";
    const desktopCollapseQuery = "(min-width: 1181px) and (hover: hover) and (pointer: fine)";
    const desktopNavStorageKey = "barrelbossDesktopNavCollapsed";
    const isMobileViewport = () => window.matchMedia(navCollapseQuery).matches;
    const isDesktopCollapseViewport = () => window.matchMedia(desktopCollapseQuery).matches;
    const setNavState = (isOpen) => {
        body.classList.toggle("nav-open", isOpen);
        if (menuButton) {
            menuButton.setAttribute("aria-expanded", String(isOpen));
        }
    };
    const openNav = () => setNavState(true);
    const closeNav = () => setNavState(false);
    const isDesktopNavCollapsed = () => body.classList.contains("desktop-nav-collapsed");
    const updateDesktopToggleUi = () => {
        if (!desktopNavToggle) {
            return;
        }

        const collapsed = isDesktopNavCollapsed();
        desktopNavToggle.setAttribute("aria-pressed", String(collapsed));
        desktopNavToggle.textContent = collapsed ? "Expand Sidebar" : "Collapse Sidebar";
    };
    const setDesktopNavCollapsed = (collapsed, persist = true) => {
        body.classList.toggle("desktop-nav-collapsed", collapsed);
        updateDesktopToggleUi();

        if (!persist) {
            return;
        }

        try {
            window.localStorage.setItem(desktopNavStorageKey, collapsed ? "1" : "0");
        } catch (_error) {
            // Keep UI working even when storage is unavailable.
        }
    };
    const getStoredDesktopCollapseState = () => {
        try {
            return window.localStorage.getItem(desktopNavStorageKey) === "1";
        } catch (_error) {
            return false;
        }
    };

    if (desktopNavToggle) {
        if (getStoredDesktopCollapseState() && isDesktopCollapseViewport()) {
            setDesktopNavCollapsed(true, false);
        } else {
            updateDesktopToggleUi();
        }

        desktopNavToggle.addEventListener("click", () => {
            if (!isDesktopCollapseViewport()) {
                return;
            }
            setDesktopNavCollapsed(!isDesktopNavCollapsed());
        });
    }

    if (menuButton && closeButton && overlay) {
        menuButton.addEventListener("click", () => {
            if (!isMobileViewport()) {
                return;
            }
            if (body.classList.contains("nav-open")) {
                closeNav();
                return;
            }

            openNav();
        });

        closeButton.addEventListener("click", closeNav);
        overlay.addEventListener("click", closeNav);

        navLinks.forEach((link) => {
            link.addEventListener("click", () => {
                if (isMobileViewport()) {
                    closeNav();
                }
            });
        });

        window.addEventListener("resize", () => {
            if (!isMobileViewport()) {
                closeNav();
            }

            if (desktopNavToggle) {
                if (
                    isDesktopCollapseViewport()
                    && getStoredDesktopCollapseState()
                    && !isDesktopNavCollapsed()
                ) {
                    setDesktopNavCollapsed(true, false);
                    return;
                }
                updateDesktopToggleUi();
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeNav();
            }
        });
    }

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
            });
        });
    }

    const insightTitle = document.getElementById("insightTitle");
    const insightDelta = document.getElementById("insightDelta");
    const insightNote = document.getElementById("insightNote");
    const metricCards = document.querySelectorAll(".metric-interactive");

    if (metricCards.length && insightTitle && insightDelta && insightNote) {
        const updateInsight = (card) => {
            insightTitle.textContent = card.dataset.insightTitle || "Live Insight";
            insightDelta.textContent = card.dataset.insightDelta || "";
            insightNote.textContent = card.dataset.insightNote || "";

            metricCards.forEach((item) => item.classList.remove("active"));
            card.classList.add("active");
        };

        metricCards.forEach((card, index) => {
            if (index === 0) {
                card.classList.add("active");
            }

            card.addEventListener("click", () => updateInsight(card));
            card.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    updateInsight(card);
                }
            });
        });
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
