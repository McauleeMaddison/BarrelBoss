(() => {
    const body = document.body;
    const menuButton = document.querySelector(".menu-btn");
    const closeButton = document.querySelector(".sidebar-close");
    const overlay = document.querySelector(".nav-overlay");
    const navLinks = document.querySelectorAll(".nav-links .nav-link");
    const isMobileViewport = () => window.matchMedia("(max-width: 980px)").matches;
    const setNavState = (isOpen) => {
        body.classList.toggle("nav-open", isOpen);
        if (menuButton) {
            menuButton.setAttribute("aria-expanded", String(isOpen));
        }
    };
    const openNav = () => setNavState(true);
    const closeNav = () => setNavState(false);

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
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeNav();
            }
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
})();
