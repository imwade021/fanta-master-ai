/* Il guardiano dell'offline.
   Al primo caricamento mette da parte l'applicazione, lo Studio e le icone.
   Da quel momento le serve dalla propria dispensa: senza rete, in aereo, in
   una taverna senza campo, l'asta funziona lo stesso.

   Le richieste alle foto dei giocatori NON si mettono in dispensa: sono
   cinquecento immagini, e senza rete l'applicazione mostra gia' le iniziali. */
const DISPENSA = 'piu3-v1';
const ROBA = [
  './', './astanote.html', './studio.html',
  './icona-180.png', './icona-192.png', './icona-512.png',
  './piu3.webmanifest', './studio.webmanifest'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(DISPENSA)
      // addAll fallisce tutto se un solo file manca: qui si prende quello che
      // c'e', perche' un'icona assente non deve impedire l'offline.
      .then(c => Promise.allSettled(ROBA.map(u => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(k => Promise.all(k.filter(x => x !== DISPENSA).map(x => caches.delete(x))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (u.origin !== location.origin) return;   // le foto restano affar loro

  e.respondWith(
    // Prima la rete, cosi' una versione nuova arriva appena c'e' campo; se non
    // risponde, la dispensa. L'ordine inverso darebbe un'applicazione che non
    // si aggiorna piu' finche' non la disinstalli.
    fetch(e.request)
      .then(r => {
        if (r && r.ok) {
          const copia = r.clone();
          caches.open(DISPENSA).then(c => c.put(e.request, copia));
        }
        return r;
      })
      .catch(() => caches.match(e.request).then(r => r || caches.match('./astanote.html')))
  );
});
