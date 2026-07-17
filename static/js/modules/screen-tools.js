(() => {
    const body = document.body;

    const filterToggleButtons = document.querySelectorAll("[data-filter-toggle]");
    filterToggleButtons.forEach((button) => {
        const filterShell = button.closest("[data-filter-shell]");
        if (!filterShell) {
            return;
        }
        const closedLabel = button.dataset.closedLabel || button.textContent.replace(/\s+/g, " ").trim();
        const openLabel = button.dataset.openLabel || closedLabel;

        const syncExpandedState = () => {
            const isOpen = filterShell.classList.contains("is-open");
            button.setAttribute(
                "aria-expanded",
                String(isOpen),
            );
            if (button.dataset.closedLabel || button.dataset.openLabel) {
                button.textContent = isOpen ? openLabel : closedLabel;
            }
        };

        syncExpandedState();

        button.addEventListener("click", () => {
            filterShell.classList.toggle("is-open");
            syncExpandedState();
        });
    });

    const instantRowForms = document.querySelectorAll("form[data-instant-submit-row]");
    instantRowForms.forEach((form) => {
        let submitted = false;

        form.addEventListener("submit", () => {
            if (submitted) {
                return;
            }
            submitted = true;

            const row = form.closest("tr");
            const button = form.querySelector("button[type='submit']");

            if (row) {
                row.classList.add("row-action-pending");
            }

            if (button) {
                button.disabled = true;
                button.classList.add("is-working");
                button.textContent = form.dataset.pendingLabel || "Working…";
            }
        });
    });

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
                    if (!cell.getAttribute("data-label")) {
                        cell.setAttribute("data-label", headerLabel || `Column ${columnIndex + 1}`);
                    }
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

    const detailDrawer = document.querySelector("[data-detail-drawer]");
    const detailBackdrop = document.querySelector("[data-detail-backdrop]");
    const detailTitle = document.querySelector("[data-detail-title]");
    const detailMeta = document.querySelector("[data-detail-meta]");
    const detailKicker = document.querySelector("[data-detail-kicker]");
    const detailBody = document.querySelector("[data-detail-body]");
    const detailCloseButtons = document.querySelectorAll("[data-detail-close]");

    if (detailDrawer && detailBackdrop && detailTitle && detailMeta && detailKicker && detailBody) {
        const closeDetailDrawer = () => {
            body.classList.remove("detail-drawer-open");
            detailDrawer.setAttribute("aria-hidden", "true");
            detailBackdrop.hidden = true;
            detailBody.replaceChildren();
        };

        const openDetailDrawer = (trigger) => {
            const templateId = trigger.dataset.detailTemplate;
            if (!templateId) {
                return;
            }

            const template = document.getElementById(templateId);
            if (!(template instanceof HTMLTemplateElement)) {
                return;
            }

            detailTitle.textContent = trigger.dataset.detailTitle || "Details";

            const metaText = trigger.dataset.detailMeta || "";
            if (metaText) {
                detailMeta.hidden = false;
                detailMeta.textContent = metaText;
            } else {
                detailMeta.hidden = true;
                detailMeta.textContent = "";
            }

            const kickerText = trigger.dataset.detailKicker || "";
            if (kickerText) {
                detailKicker.hidden = false;
                detailKicker.textContent = kickerText;
            } else {
                detailKicker.hidden = true;
                detailKicker.textContent = "";
            }

            detailBody.replaceChildren(document.importNode(template.content, true));
            detailBackdrop.hidden = false;
            detailDrawer.setAttribute("aria-hidden", "false");
            body.classList.add("detail-drawer-open");

            const focusTarget = detailDrawer.querySelector("[data-detail-close]") || detailDrawer;
            window.requestAnimationFrame(() => {
                if (focusTarget instanceof HTMLElement) {
                    focusTarget.focus();
                }
            });
        };

        document.addEventListener("click", (event) => {
            const trigger = event.target.closest("[data-detail-trigger]");
            if (trigger) {
                openDetailDrawer(trigger);
                return;
            }

            if (event.target.closest("[data-detail-close]") || event.target === detailBackdrop) {
                closeDetailDrawer();
            }
        });

        detailCloseButtons.forEach((button) => {
            button.addEventListener("click", closeDetailDrawer);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && body.classList.contains("detail-drawer-open")) {
                closeDetailDrawer();
            }
        });
    }
})();
