import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Node 20+ ships a spec-compliant WebCrypto on globalThis, so the crypto
    // paths (HMAC, AES-GCM, PBKDF2, SPKI import) run unmocked here. Only the
    // Web Bluetooth layer needs a fake - it has no Node equivalent, which is
    // exactly why the transport sits behind an interface.
    environment: 'node',
    include: ['packages/*/tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'json-summary', 'lcov'],
      reportsDirectory: 'coverage',
      include: ['packages/*/src/**/*.ts'],
      exclude: [
        // Thin wrappers over browser APIs with no Node equivalent to fake -
        // navigator.bluetooth and getUserMedia/BarcodeDetector. Their decision
        // logic lives in deviceCapabilities()/isQrScanningAvailable(), which
        // are covered; what remains is glue that only hardware can exercise.
        'packages/hoermoles-ble-js/src/web-bluetooth.ts',
        'packages/webapp/src/lib/qr.ts',
        'packages/webapp/src/main.ts',
        'packages/webapp/src/**/*.svelte',
        'packages/webapp/src/**/*.svelte.ts',
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
});
