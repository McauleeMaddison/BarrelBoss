(() => {
    const panelStorageKey = "barrelboss-dashboard-panel-state";
    const accordionStorageKey = "barrelboss-dashboard-accordion-state";
    const motionCurve = "cubic-bezier(0.22, 1, 0.36, 1)";
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const collapsiblePanels = document.querySelectorAll(".dashboard-collapsible[data-panel-storage-key]");
    const accordionGroups = document.querySelectorAll("[data-dashboard-accordion-group]");
    const accordionControllers = new Map();
    const accordionBodyControllers = new Map();
    const panelControllers = new Map();

    const clearBodyAnimation = (body) => {
        if (body._dashboardAnimationFrame) {
            window.cancelAnimationFrame(body._dashboardAnimationFrame);
        }

        if (body._dashboardAnimationTimeout) {
            window.clearTimeout(body._dashboardAnimationTimeout);
        }

        if (body._dashboardAnimationCleanup) {
            body._dashboardAnimationCleanup();
        }

        body._dashboardAnimationFrame = null;
        body._dashboardAnimationTimeout = null;
        body._dashboardAnimationCleanup = null;
    };

    const finishBodyVisibility = (body, state) => {
        clearBodyAnimation(body);
        body.hidden = state === "closed";
        body.dataset.dashboardVisibility = state;
        body.style.transition = "";
        body.style.height = "";
        body.style.opacity = "";
        body.style.overflow = "";
    };

    const setBodyVisibility = (body, isOpen, { animate = true } = {}) => {
        if (!body) {
            return;
        }

        const nextState = isOpen ? "open" : "closed";
        clearBodyAnimation(body);

        if (!animate || prefersReducedMotion) {
            finishBodyVisibility(body, nextState);
            return;
        }

        const startHeight = body.hidden ? 0 : body.getBoundingClientRect().height;
        body.hidden = false;
        const targetHeight = isOpen ? body.scrollHeight : 0;

        body.style.transition = "none";
        body.style.overflow = "hidden";
        body.style.height = `${startHeight}px`;
        body.style.opacity = isOpen ? (startHeight === 0 ? "0" : "1") : "1";
        body.dataset.dashboardVisibility = isOpen ? "opening" : "closing";
        void body.offsetHeight;

        const handleTransitionEnd = (event) => {
            if (event.target !== body || event.propertyName !== "height") {
                return;
            }

            finishBodyVisibility(body, nextState);
        };

        body.addEventListener("transitionend", handleTransitionEnd);
        body._dashboardAnimationCleanup = () => {
            body.removeEventListener("transitionend", handleTransitionEnd);
        };

        body._dashboardAnimationFrame = window.requestAnimationFrame(() => {
            body.style.transition = `height 340ms ${motionCurve}, opacity 220ms ease`;
            body.style.height = `${targetHeight}px`;
            body.style.opacity = isOpen ? "1" : "0";
        });

        body._dashboardAnimationTimeout = window.setTimeout(() => {
            finishBodyVisibility(body, nextState);
        }, 420);
    };

    const readPanelState = () => {
        try {
            return JSON.parse(window.localStorage.getItem(panelStorageKey) || "{}");
        } catch (_error) {
            return {};
        }
    };

    const writePanelState = (state) => {
        try {
            window.localStorage.setItem(panelStorageKey, JSON.stringify(state));
        } catch (_error) {
            // Ignore storage errors.
        }
    };

    const readAccordionState = () => {
        try {
            return JSON.parse(window.localStorage.getItem(accordionStorageKey) || "{}");
        } catch (_error) {
            return {};
        }
    };

    const writeAccordionState = (state) => {
        try {
            window.localStorage.setItem(accordionStorageKey, JSON.stringify(state));
        } catch (_error) {
            // Ignore storage errors.
        }
    };

    if (accordionGroups.length) {
        const storedAccordionState = readAccordionState();

        accordionGroups.forEach((group) => {
            const groupKey = group.dataset.dashboardAccordionGroup;
            const items = Array.from(group.querySelectorAll("[data-dashboard-accordion-item]"));

            if (!groupKey || !items.length) {
                return;
            }

            const getItemParts = (item) => ({
                key: item.dataset.dashboardAccordionKey,
                trigger: item.querySelector("[data-dashboard-accordion-trigger]"),
                body: item.querySelector("[data-dashboard-accordion-body]"),
            });

            const defaultItem =
                items.find((item) => item.dataset.dashboardAccordionDefaultOpen === "true") || items[0];
            let openKey = Object.prototype.hasOwnProperty.call(storedAccordionState, groupKey)
                ? storedAccordionState[groupKey]
                : defaultItem?.dataset.dashboardAccordionKey || null;

            const applyAccordionState = (nextOpenKey, { animate = true } = {}) => {
                items.forEach((item) => {
                    const { key, trigger, body } = getItemParts(item);
                    const isOpen = Boolean(nextOpenKey) && key === nextOpenKey;

                    item.classList.toggle("is-open", isOpen);

                    if (trigger) {
                        trigger.setAttribute("aria-expanded", String(isOpen));
                    }

                    if (body) {
                        setBodyVisibility(body, isOpen, { animate });
                        if (body.id) {
                            accordionBodyControllers.set(body.id, { groupKey, key });
                        }
                    }
                });
            };

            const setOpenKey = (nextOpenKey) => {
                openKey = nextOpenKey;
                storedAccordionState[groupKey] = openKey;
                writeAccordionState(storedAccordionState);
                applyAccordionState(openKey);
            };

            accordionControllers.set(groupKey, { setOpenKey });
            applyAccordionState(openKey, { animate: false });

            items.forEach((item) => {
                const { key, trigger } = getItemParts(item);

                if (!key || !trigger) {
                    return;
                }

                trigger.addEventListener("click", () => {
                    setOpenKey(openKey === key ? null : key);
                });
            });
        });
    }

    if (collapsiblePanels.length) {
        const storedPanelState = readPanelState();

        collapsiblePanels.forEach((panel) => {
            const storageId = panel.dataset.panelStorageKey;
            const toggle = panel.querySelector("[data-panel-toggle]");
            const body = panel.querySelector("[data-panel-body]");

            if (!storageId || !toggle || !body) {
                return;
            }

            const hasStoredState = Object.prototype.hasOwnProperty.call(storedPanelState, storageId);
            const defaultCollapsed = panel.dataset.panelDefaultCollapsed === "true";

            const applyState = (isCollapsed, { animate = true } = {}) => {
                setBodyVisibility(body, !isCollapsed, { animate });
                toggle.setAttribute("aria-expanded", String(!isCollapsed));
                toggle.textContent = isCollapsed ? "Expand" : "Collapse";
                panel.classList.toggle("is-collapsed", isCollapsed);
            };

            const setCollapsed = (isCollapsed) => {
                storedPanelState[storageId] = isCollapsed;
                writePanelState(storedPanelState);
                applyState(isCollapsed);
            };

            if (body.id) {
                panelControllers.set(body.id, { setCollapsed });
            }

            applyState(hasStoredState ? Boolean(storedPanelState[storageId]) : defaultCollapsed, {
                animate: false,
            });

            toggle.addEventListener("click", () => {
                setCollapsed(!panel.classList.contains("is-collapsed"));
            });
        });
    }

    const activateHashTarget = (hashId) => {
        if (!hashId) {
            return;
        }

        const target = document.getElementById(hashId);
        if (!target) {
            return;
        }

        const owningAccordionBody =
            target.matches("[data-dashboard-accordion-body]")
                ? target
                : target.closest("[data-dashboard-accordion-body]");
        if (owningAccordionBody?.id) {
            const accordionState = accordionBodyControllers.get(owningAccordionBody.id);
            if (accordionState) {
                accordionControllers.get(accordionState.groupKey)?.setOpenKey(accordionState.key);
            }
        }

        const owningPanelBody =
            target.matches("[data-panel-body]") ? target : target.closest("[data-panel-body]");
        if (owningPanelBody?.id) {
            panelControllers.get(owningPanelBody.id)?.setCollapsed(false);
        }

        const shouldDelayScroll = Boolean(owningAccordionBody || owningPanelBody) && !prefersReducedMotion;
        window.setTimeout(
            () => {
                target.scrollIntoView({ block: "start", behavior: "smooth" });
            },
            shouldDelayScroll ? 170 : 0,
        );
    };

    const syncHashTarget = () => {
        activateHashTarget(window.location.hash.replace(/^#/, ""));
    };

    if (window.location.hash) {
        syncHashTarget();
    }

    window.addEventListener("hashchange", syncHashTarget);
    document.addEventListener("click", (event) => {
        const link = event.target.closest("a[href*='#']");
        if (!link) {
            return;
        }

        const nextUrl = new URL(link.href, window.location.href);
        const sameDocument =
            nextUrl.origin === window.location.origin
            && nextUrl.pathname === window.location.pathname
            && nextUrl.search === window.location.search;

        if (sameDocument && nextUrl.hash) {
            activateHashTarget(nextUrl.hash.replace(/^#/, ""));
        }
    });

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
})();
