# SPA plan: Hoermoles web app (PWA on GitHub Pages)

Status: **steps 2-6 implemented, steps 1 and 7 outstanding.** Target URL
`https://the78mole.github.io/hoermoles-ble/`.

> **The two hardware spikes have not been run.** Everything below is built and green in CI,
> but nothing in this repository has yet spoken to a real drive over Web Bluetooth. Spike 1
> in particular (section 9, risk 1) can still invalidate the approach - do it before
> trusting any of this in the driveway.

Goal: a browser app that talks the BlueSecur "Signed" BLE protocol directly via Web
Bluetooth - installable on a phone, fully offline after first load, no app store, no cloud.
It must be able to both **import credentials registered with the Python CLI** and **register
a drive on its own**.

Decisions already fixed:

- Package manager: **npm** (workspaces), not pnpm.
- Registration (QR scan + RSA) is **in scope for v1**, not deferred.
- **iOS is explicitly out of scope** - Safari has no Web Bluetooth at all. Someone else can
  port that (Bluefy/WebBLE or a native wrapper). The README will say so plainly rather than
  pretend.
- Build tool: **Vite**. Framework: **Svelte 5 + TypeScript**. Svelte compiles away, so the
  dependency footprint stays close to vanilla - which matters for something holding a door
  key - while the menu editor in step 7 (roughly 60 settings rendered from
  `menu-tables.json`) gets real data binding instead of hand-rolled DOM updates.

## 1. Hard constraints - these drive the design, not taste

| Capability | Status | Consequence for us |
| --- | --- | --- |
| GATT connect / write / notify | shipped (Chrome+Edge on Android, ChromeOS, Windows, macOS) | The core feature (trigger a channel) works |
| Chrome on **Linux desktop** | needs `chrome://flags/#enable-experimental-web-platform-features` | Dev machines must set the flag |
| **iOS / Safari** | not implemented | Out of scope, see above |
| Firefox (any platform) | not implemented, no plans | Out of scope |
| `manufacturerData` filter in `requestDevice()` | shipped since Chrome 92 | Device chooser can be narrowed to Hoermann drives only |
| `watchAdvertisements()` / reading advertisement data | behind the experimental flag | **No port of `advertisement.py` in v1.** No gate status, no opening percentage, no serial-number matching without connecting |
| `getDevices()` (remember a permitted device across sessions) | behind the experimental flag | User must pick the drive in the browser chooser once per app start. Must be **feature-detected**, never assumed |
| **RSA PKCS#1 v1.5 encryption** | not in WebCrypto (only RSA-OAEP encrypt / RSASSA-PKCS1-v1_5 *sign*) | Registration needs a hand-rolled implementation - see section 5 |
| HMAC-SHA256 | WebCrypto, and supports **non-extractable** keys | Root key can be stored so it cannot be read back out |

The chooser requirement is the main UX consequence: as long as the PWA stays resident we
hold the GATT connection open and "impulse" is one tap. After a cold start it is two taps
(button -> chooser -> connect -> send). With the experimental flag plus `getDevices()` it
drops back to one - the app should light that path up when available and degrade quietly
when not.

## 2. Repository layout

```text
spa/
  package.json                  # npm workspaces root
  packages/
    hoermoles-ble-js/           # dependency-free TS port of protocol.py
      src/{protocol,bundle,rsa-pkcs1,crypto,transport}.ts
    webapp/                     # Vite + Svelte + PWA + Web Bluetooth transport + UI
shared/
  test-vectors.json             # consumed by BOTH pytest and vitest
  menu-tables.json              # generated from menu_settings.py
```

Workspace layout from day one: it costs nothing, mirrors `python/packages/*`, and the root
README already announces ports to other languages. **No npm publishing in v1** - only the
Pages deploy. `hoermoles-ble-js` can be published later if anything else ever wants to
`npm install` it.

## 3. Protocol port

`protocol.py` was deliberately written free of any BLE/crypto library dependency, so the
port is close to mechanical: outer envelope, `_build_signed_frame`, `NotificationReassembler`,
and every parser. A `BleTransport` interface mirroring the Python one, implemented by
`WebBluetoothTransport` using `writeValueWithoutResponse()` (the equivalent of bleak's
`response=False`).

**Correctness is enforced, not hoped for:** export test vectors from the existing pytest
suite into `shared/test-vectors.json` (frames, HMACs, notification payloads, QR prefix
parsing, root-key derivation) and run *both* suites against them. The TS port then cannot
drift from the Python reference without CI going red.

Same trick for the menu table (555 lines of data in `menu_settings.py`): generate
`shared/menu-tables.json` from Python, and have CI verify it is in sync rather than
maintaining a second hand-written copy.

## 4. Credential bundle - moving the root key between Python and the SPA

One versioned, language-neutral format, implemented on both sides from the same spec
(`hoermoles_ble/bundle.py` and `bundle.ts`):

```json
{ "v": 1, "devices": [{
    "address": "F1:26:AF:CC:41:86", "root_id": 1, "root_key": "<hex>",
    "qr_prefix": "...", "product_class": 2, "product_id": 2,
    "product_name": "Supramatic Serie 4", "serial_no": 302626026414510307,
    "created_unix": 1784850177 }]}
```

Text form: `HMOLES1:<base64url(json)>`, or `HMOLES1E:<base64url(salt|iv|ciphertext)>` for
the AES-256-GCM / PBKDF2-SHA256 encrypted variant. Both are native to WebCrypto and to
`cryptography`, which the Python side already depends on.

### Transport paths, in build order

1. **File** - `hoermoles-ble export --address <MAC> --out drive.json`, imported in the SPA
   via `<input type="file">`, drag & drop, or paste. Simplest, works offline, no camera
   permission needed. Sufficient on its own.
2. **QR code** - `hoermoles-ble export --qr` renders the bundle string straight into the
   terminal (`segno`, pure Python, tiny). The SPA scans it with `BarcodeDetector` (native in
   Chrome on Android) falling back to `zxing-wasm`. Payload is roughly 200 characters, well
   within a small QR version. This is the nicest flow: terminal on the desktop, phone held
   in front of it, done.
3. **Deep link** - `.../hoermoles-ble/#import=HMOLES1E:...`. The fragment never leaves the
   browser, so GitHub Pages never sees it. Convenient, but it does land in browser history
   and clipboard - offer this **only** with the encrypted variant.

**Reverse direction, symmetric:** the SPA can export the same bundle (QR on screen or file
download) and `hoermoles-ble import <file|text>` reads it back. That is what makes a drive
registered on the phone usable from the CLI and later from Home Assistant.

New on the Python side: `hoermoles_ble/bundle.py`, CLI commands `export` and `import`, and
`segno` as a dependency of the CLI package.

### Handling the secret

The root key is a house key. Accordingly:

- After import, store it as a **non-extractable** HMAC `CryptoKey` in IndexedDB (`CryptoKey`
  survives structured clone). A later XSS then gets at most a signing oracle, not the key
  itself - and a signing oracle is useless without BLE proximity to the door.
- Re-export from the SPA requires an extractable copy, so make that an explicit opt-in
  toggle ("allow exporting this credential again") rather than the default.
- Ship a CSP meta tag with `connect-src 'none'`. The app needs **zero** network access after
  load, so this cheaply removes the exfiltration channel entirely.
- Plaintext QR export prints a loud warning; encrypted export is the documented default for
  anything that leaves the machine.

## 5. Registration inside the SPA (in scope for v1)

Phase 1 of `client.register()` needs RSAES-PKCS1-v1_5 encryption of a 32-byte random
register key. WebCrypto cannot do it. The workaround is small and fully testable:

1. `crypto.subtle.importKey('spki', der, {name: 'RSA-OAEP', hash: 'SHA-256'}, true, ['encrypt'])`
   then `exportKey('jwk')` to get the modulus `n` and exponent `e` as base64url - this reuses
   the browser's DER parser instead of hand-writing an ASN.1 walker.
2. Build the PKCS#1 v1.5 type-2 padded block: `0x00 || 0x02 || PS || 0x00 || M`, with `PS`
   being `k - mLen - 3` random **non-zero** bytes.
3. `c = m^e mod n` with `BigInt` square-and-multiply. With `e = 65537` that is 17 iterations.

Everything after that (REGISTER_ROOT frame, ROOT_KEY notification, `derive_root_key` XOR) is
plain HMAC and byte handling, i.e. already covered by the protocol port.

QR scanning for the registration itself uses the same scanner component as bundle import -
one code path, two payload types, distinguished by prefix.

## 6. PWA and GitHub Pages

- `vite-plugin-pwa` (Workbox): manifest, service worker, precache of the whole app shell, so
  the app is **fully usable offline** after the first load. Auto-update prompt on new deploys.
- `base: '/hoermoles-ble/'` in `vite.config.ts`.
- Maskable icons, `theme_color`, `display: standalone`. Android install prompt via
  `beforeinstallprompt`.
- One-time manual step: repo Settings -> Pages -> Source = "GitHub Actions".

## 7. CI

- **`spa-test.yml`** - vitest + `@vitest/coverage-v8`, job summary, and a second badge file
  `hoermoles-spa-coverage.json` in the *same* gist already used for Python coverage.
- **`spa-deploy.yml`** - one file: test -> `paulhatch/semantic-version` with
  `tag_prefix: "spa/v"` -> GitHub Release -> build -> `actions/upload-pages-artifact` ->
  `actions/deploy-pages`. Triggered on `paths: ['spa/**', 'shared/**', '.github/workflows/spa-*.yml']`.
  Needs `permissions: {pages: write, id-token: write}`.
- **Fix an existing bug while we are here:** `.github/workflows/pypi-publish.yml` triggers on
  `paths: ['python/**', '.github/workflows/*.yml']`. As written, every edit to a SPA workflow
  file would cut a Python release. Narrow it to `pypi-publish.yml` and `test.yml`.
- Pre-commit: `local` hooks calling `npm run lint` / `npm run format` (see the
  `spa-project-setup` skill). `.gitignore` gains `node_modules/`, `dist/`, `coverage/`.
- README badge row gains the deploy-status badge and the SPA coverage badge - same row, not
  a second one.

## 8. Build order

| # | Step | Status | Outcome |
| --- | --- | --- | --- |
| **Spike 0** | Test page on the target phone: `requestDevice`, connect, notify; feature-detect `getDevices()` / `watchAdvertisements()` | **outstanding** | Settles whether devices can be remembered across sessions. The app already feature-detects both and degrades, so this confirms behaviour rather than gating code |
| **Spike 1** | Write a Signed frame in 20-byte chunks and trigger an impulse on real hardware | **outstanding** | See section 9, risk 1. Was meant to go first; the rest was built ahead of it because all of it is independently testable, but the risk is unchanged |
| 2 | Bundle spec + `export`/`import` in Python (file + QR) | done | `hoermoles_ble.bundle`, CLI `export`/`import`, segno QR, 20 tests |
| 3 | TS protocol port + shared test vectors + vitest | done | `hoermoles-ble-js`, byte-identical to Python against `shared/test-vectors.json`; 106 tests, 90% coverage |
| 4 | Webapp MVP: import (file/QR), device picker, channel buttons | done | Svelte 5 + Vite, ~29 kB gzipped |
| 5 | PWA shell + Pages deploy + CI + badges | done | `spa-test.yml` / `spa-deploy.yml`, icons from `shared/assets`, CSP with `connect-src 'none'` |
| 6 | Registration in the SPA (camera QR + BigInt RSA) | done | `rsa-pkcs1.ts`, round-trip tested against generated RSA key pairs |
| 7 | Menu editor, log/service views, advertisement status (flag-gated) | **outstanding** | `menu-tables.ts` and `client.readProperties`/`readLog`/`readServiceData` exist and are tested; only the UI is missing. Advertisement status stays impossible without the browser flag |

## 9. Risks

1. **The chunk-write timing window - still open, and still the one that can sink this.** Live
   testing showed the drive disconnects roughly 100-150 ms after the first chunk, regardless
   of chunk count - it behaves like a fixed time budget for the whole message. Web Bluetooth
   serialises GATT operations through the browser process and is measurably slower than bleak.
   If a full frame cannot be pushed inside that window, the entire SPA is dead in the water.
   `WebBluetoothTransport.write()` and `HoermannClient.writeChunked()` are written to do the
   least possible work per chunk, but no amount of care in the code substitutes for measuring
   it against the real drive. A channel command is 49 bytes, i.e. three writes.
2. **No persistent device without the experimental flag.** A UX compromise, not a blocker.
3. **Unverified protocol paths.** `write_properties` and channels 2-6 are, per their own
   docstrings, not verified against real hardware. The SPA must not present them as if they
   were - mark them clearly in the UI.
4. **Supply chain.** Serving a door-opening app from GitHub Pages means a repo compromise is
   a door compromise. Mitigated by the non-extractable key, `connect-src 'none'`, and the
   service worker keeping an installed PWA on its cached build - but worth stating in the
   README rather than glossing over.
