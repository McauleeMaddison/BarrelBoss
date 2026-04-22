const CACHE_NAME = "barrelboss-shell-v3";
const APP_SHELL = [
    "/",
    "/accounts/login/",
    "/static/css/app.css",
    "/static/js/app.js",
    "/static/js/pwa.js",
    "/static/images/barrelboss-logo.png",
    "/static/images/pwa-192.png",
    "/static/images/pwa-512.png"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") {
        return;
    }

    const requestUrl = new URL(event.request.url);
    if (requestUrl.origin !== self.location.origin) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                return cachedResponse;
            }

            return fetch(event.request)
                .then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200 && networkResponse.type === "basic") {
                        const responseToCache = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseToCache);
                        });
                    }
                    return networkResponse;
                })
                .catch(() => caches.match("/accounts/login/"));
        })
    );
});

self.addEventListener("push", (event) => {
    let payload = {};
    if (event.data) {
        try {
            payload = event.data.json();
        } catch (_error) {
            payload = { body: event.data.text() };
        }
    }

    const title = payload.title || "BarrelBoss";
    const options = {
        body: payload.body || "You have a new update.",
        icon: payload.icon || "/static/images/pwa-192.png",
        badge: payload.badge || "/static/images/pwa-192.png",
        tag: payload.tag || "barrelboss-update",
        renotify: Boolean(payload.renotify),
        data: {
            url: payload.url || "/dashboard/",
            ...payload.data,
        },
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) || "/dashboard/";

    event.waitUntil(
        clients
            .matchAll({ type: "window", includeUncontrolled: true })
            .then((windowClients) => {
                for (const client of windowClients) {
                    if ("focus" in client && client.url.includes(targetUrl)) {
                        return client.focus();
                    }
                }

                if (clients.openWindow) {
                    return clients.openWindow(targetUrl);
                }

                return null;
            })
    );
});
