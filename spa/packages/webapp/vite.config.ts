import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig, type Plugin } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// GitHub Pages project site. The app deliberately lives in an `app/`
// subdirectory rather than at the site root, leaving `/hoermoles-ble/` free for
// other generated content (documentation, and whatever comes later) - see
// `pages/` and the site-assembly step in spa-deploy.yml.
//
// Every asset URL, the manifest's start_url/scope and the service worker scope
// derive from this, so it must match wherever the site is actually served from.
// Overridable for local preview and for anyone hosting the app at a domain root.
const base = process.env.HOERMOLES_BASE ?? '/hoermoles-ble/app/';

/**
 * Content-Security-Policy, injected here rather than hardcoded in index.html
 * because dev and production genuinely need different policies.
 *
 * Production is the strict one and the one that matters: this app holds root
 * keys that open a physical garage door, and it needs no network access at all
 * once loaded. `connect-src 'none'` therefore removes the exfiltration channel
 * outright - even if the page were compromised, a stolen credential has
 * nowhere to go. Do not loosen it without a very good reason.
 *
 * Dev has to allow the HMR websocket, or hot reload silently dies (which is
 * exactly what happened before this plugin existed - the browser blocked
 * `ws://localhost:5173` and every edit needed a manual refresh).
 *
 * `frame-ancestors` is deliberately absent: browsers ignore it in a <meta> tag
 * and log a warning. It only works as a real HTTP header, which GitHub Pages
 * does not let us set.
 */
function csp(): Plugin {
  const shared = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ];

  return {
    name: 'hoermoles-csp',
    transformIndexHtml(_html, ctx) {
      const connectSrc = ctx.server
        ? "connect-src 'self' ws: wss:" // dev only: Vite HMR
        : "connect-src 'none'";
      return [
        {
          tag: 'meta',
          attrs: {
            'http-equiv': 'Content-Security-Policy',
            content: [...shared, connectSrc].join('; '),
          },
          injectTo: 'head-prepend',
        },
      ];
    },
  };
}

export default defineConfig({
  base,
  plugins: [
    csp(),
    svelte(),
    VitePWA({
      registerType: 'prompt',
      // The app needs no network at all after loading - precaching the whole
      // shell makes it genuinely offline-capable, which matters for a garage
      // that may have no signal.
      workbox: {
        // webp covers the splash and the page background; without it those were
        // silently left out of the offline precache.
        globPatterns: ['**/*.{js,css,html,svg,png,webp,ico,woff2}'],
        // menu-tables.json is ~250 kB; the default 2 MiB limit is fine but be
        // explicit so a future data file does not silently drop out of the cache.
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      manifest: {
        name: 'Hoermoles',
        short_name: 'Hoermoles',
        description: 'Control Hoermann BlueSecur drives over Bluetooth, without the vendor app or cloud',
        theme_color: '#1b2733',
        background_color: '#1b2733',
        display: 'standalone',
        orientation: 'portrait',
        start_url: base,
        scope: base,
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  build: {
    target: 'es2022',
    sourcemap: true,
  },
});
