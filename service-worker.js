const CACHE_NAME = 'pausecheck-shell-v2';
const APP_FILES = [
  './',
  './index.html',
  './styles.css',
  './app.js',
  './model.json',
  './manifest.webmanifest',
  './icon.svg'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('pausecheck-shell-') && key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  const knownFile = APP_FILES.some(file => url.pathname.endsWith(file.replace('./', '/')) || (file === './' && url.pathname.endsWith('/')));
  if (!knownFile) return;
  event.respondWith(fetch(request).then(response => {
    if (response && response.ok) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(async () => {
    const cached = await caches.match(request, { ignoreSearch: true });
    return cached || new Response('PauseCheck is offline and this app file is not cached yet.', { status: 503, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  }));
});
