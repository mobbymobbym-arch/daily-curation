const CACHE_NAME = 'dark-chess-v1';
const ASSETS = [
    'dark_chess.html',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@900&display=swap',
    'https://www.transparenttextures.com/patterns/sandpaper.png',
    'https://www.transparenttextures.com/patterns/chinese-lantern.png',
    'https://www.transparenttextures.com/patterns/handmade-paper.png',
    'https://www.transparenttextures.com/patterns/dark-wood.png',
    'https://www.transparenttextures.com/patterns/marble-similar.png'
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
    );
});

self.addEventListener('fetch', (e) => {
    e.respondWith(
        caches.match(e.request).then((res) => res || fetch(e.request))
    );
});
