(() => {
    const pushSettingsNode = document.querySelector("[data-push-settings]");
    const pushStatus = document.getElementById("pushStatus");

    if (!pushSettingsNode || !pushStatus) {
        return;
    }

    const enableButton = pushSettingsNode.querySelector("[data-push-enable]");
    const disableButton = pushSettingsNode.querySelector("[data-push-disable]");
    const vapidPublicKey = pushSettingsNode.dataset.vapidPublicKey || "";
    const subscribeUrl = pushSettingsNode.dataset.subscribeUrl || "";
    const unsubscribeUrl = pushSettingsNode.dataset.unsubscribeUrl || "";
    const pushConfigured = pushSettingsNode.dataset.configured === "true";
    const initialEnabled = pushSettingsNode.dataset.initialEnabled === "true";
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');

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
        return (
            pushSettingsNode.dataset.csrfToken
            || (csrfMeta ? csrfMeta.getAttribute("content") || "" : "")
        ).trim();
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
            credentials: "same-origin",
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
})();
