(() => {
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
