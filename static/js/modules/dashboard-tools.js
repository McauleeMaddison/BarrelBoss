(() => {
    const panelStorageKey = "barrelboss-dashboard-panel-state";
    const accordionStorageKey = "barrelboss-dashboard-accordion-state";
    const collapsiblePanels = document.querySelectorAll(".dashboard-collapsible[data-panel-storage-key]");
    const accordionGroups = document.querySelectorAll("[data-dashboard-accordion-group]");

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

            const applyAccordionState = (nextOpenKey) => {
                items.forEach((item) => {
                    const { key, trigger, body } = getItemParts(item);
                    const isOpen = Boolean(nextOpenKey) && key === nextOpenKey;

                    item.classList.toggle("is-open", isOpen);

                    if (trigger) {
                        trigger.setAttribute("aria-expanded", String(isOpen));
                    }

                    if (body) {
                        body.hidden = !isOpen;
                    }
                });
            };

            applyAccordionState(openKey);

            items.forEach((item) => {
                const { key, trigger } = getItemParts(item);

                if (!key || !trigger) {
                    return;
                }

                trigger.addEventListener("click", () => {
                    openKey = openKey === key ? null : key;
                    storedAccordionState[groupKey] = openKey;
                    writeAccordionState(storedAccordionState);
                    applyAccordionState(openKey);
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

            const applyState = (isCollapsed) => {
                body.hidden = isCollapsed;
                toggle.setAttribute("aria-expanded", String(!isCollapsed));
                toggle.textContent = isCollapsed ? "Expand" : "Collapse";
                panel.classList.toggle("is-collapsed", isCollapsed);
            };

            applyState(hasStoredState ? Boolean(storedPanelState[storageId]) : defaultCollapsed);

            toggle.addEventListener("click", () => {
                const nextCollapsed = !panel.classList.contains("is-collapsed");
                storedPanelState[storageId] = nextCollapsed;
                writePanelState(storedPanelState);
                applyState(nextCollapsed);
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
})();
