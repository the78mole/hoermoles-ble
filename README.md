# Hoermoles

[![PyPI - hoermoles-ble](https://img.shields.io/pypi/v/hoermoles-ble?label=hoermoles-ble)](https://pypi.org/project/hoermoles-ble/)
[![PyPI - hoermoles-ble-cli](https://img.shields.io/pypi/v/hoermoles-ble-cli?label=hoermoles-ble-cli)](https://pypi.org/project/hoermoles-ble-cli/)
[![Release](https://github.com/the78mole/hoermoles-ble/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/the78mole/hoermoles-ble/actions/workflows/pypi-publish.yml)
[![Tests](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml/badge.svg)](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/the78mole/42b377cb18c21fa8d1cfee3fc3bc3605/raw/hoermoles-ble-coverage.json)](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml)
[![Web app](https://github.com/the78mole/hoermoles-ble/actions/workflows/spa-deploy.yml/badge.svg)](https://the78mole.github.io/hoermoles-ble/app/)
[![SPA Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/the78mole/42b377cb18c21fa8d1cfee3fc3bc3605/raw/hoermoles-spa-coverage.json)](https://github.com/the78mole/hoermoles-ble/actions/workflows/spa-test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com)

[![Open the web app](https://img.shields.io/badge/%F0%9F%9A%AA%20Open%20the%20web%20app-the78mole.github.io%2Fhoermoles--ble%2Fapp-4aa8ff?style=for-the-badge)](https://the78mole.github.io/hoermoles-ble/app/)

*Needs Chrome or Edge (Android, Windows, macOS, ChromeOS) - Safari and Firefox have no Web
Bluetooth, so iOS cannot control a drive. See [Web app](#web-app).*

Independent control of Hoermann garage door drives that use the BlueSecur BLE
"Signed" protocol, without relying on the official app/cloud.

## Layout

- `python/` - uv workspace with the Python packages:
  - `hoermoles-ble` - protocol/crypto core + BLE client (`packages/hoermoles-ble`)
  - `hoermoles-ble-cli` - test tool/CLI (`packages/hoermoles-ble-cli`)
  - `hoermoles-ble-homeassistant` - Home Assistant integration (placeholder, not implemented yet)
- `spa/` - npm workspace for the web app:
  - `hoermoles-ble-js` - TypeScript port of the protocol + a Web Bluetooth transport
  - `webapp` - the installable PWA itself
- `shared/` - **generated** language-neutral artifacts consumed by both sides
  (`test-vectors.json`, `menu-tables.json`) plus the app artwork. Do not edit by
  hand; see [Shared artifacts](#shared-artifacts).
- `pages/` - the published site's root. The deploy copies this to the top level
  and grafts the built app in at `app/`, so further content (documentation) can
  be added here as a sibling without colliding with the app's asset tree or its
  service worker scope. `make site` assembles the same layout locally.

`python/packages/hoermoles-ble/src/hoermoles_ble/protocol.py` remains the
dependency-free reference implementation - further ports to other languages
should start from it and from `shared/test-vectors.json`.

## Quickstart

### CLI

```bash
uv tool install hoermoles-ble-cli
hoermoles-ble scan
```

Working on this repo instead? `cd python && uv sync`, then prefix commands
with `uv run` - see `python/README.md`.

### Web app

<https://the78mole.github.io/hoermoles-ble/app/> - installable to the home screen
and fully offline-capable after the first load.

**Browser support is the limiting factor, not the app.** Web Bluetooth is
implemented by Chrome and Edge on Android, Windows, macOS and ChromeOS; on Linux
it additionally needs `chrome://flags/#enable-experimental-web-platform-features`.
Safari and Firefox do not implement it at all, so **iOS/iPadOS cannot control a
drive** - contributions porting this to a platform that can are welcome.

Two further consequences of Web Bluetooth's current state, both flag-gated and
both handled by feature detection rather than assumed:

- Reading advertisement data (gate status, opening percentage) is not possible,
  so the web app has no equivalent of the CLI's `scan` output.
- Remembering a drive between app starts is not possible either, so you pick it
  from the browser's Bluetooth chooser once per session.

### Moving credentials between the CLI and the web app

The web app cannot read `~/.hoermoles`, so credentials travel as a versioned
bundle (`hoermoles_ble.bundle` / `spa/packages/hoermoles-ble-js/src/bundle.ts` -
one spec, two implementations):

```bash
hoermoles-ble export                   # QR code in the terminal, scan it with the app
hoermoles-ble export --stdout          # just the bundle text, to copy or pipe
hoermoles-ble export --encrypt         # passphrase-protected (AES-256-GCM)
hoermoles-ble export --out drive.json  # a file to load in the app instead
hoermoles-ble import <file|text|->     # the reverse direction, e.g. from the app
```

Progress messages and warnings go to stderr, so `--stdout` yields exactly one
line and composes:

```bash
hoermoles-ble export --stdout | ssh other-host hoermoles-ble import -
hoermoles-ble export --stdout > backup.txt
```

A root key opens a physical door. Prefer `--encrypt` for anything that leaves
the machine, and note that the app stores imported keys **non-extractably** by
default - it can sign door commands afterwards but can never hand the key on
again unless you explicitly opt into re-export.

Drives can also be registered directly in the web app (camera QR scan), with no
CLI involved at all. The app's **Export** tab does the reverse too - it shows a
credential as a QR code to scan from another phone, or builds a shareable link.
That link carries the credential in its URL `#` fragment, which browsers never
send to a server (so a static GET host like Pages never sees it), but which does
persist in history and chat previews - so links are offered for the encrypted
export only, and the recipient still needs the passphrase.

## Shared artifacts

`shared/test-vectors.json` and `shared/menu-tables.json` are generated from the
Python implementation and consumed by the TypeScript test suite. That is what
keeps the port byte-identical rather than merely plausible.

```bash
cd python && uv run python scripts/generate_shared.py
```

`test_interop.py` fails if the committed files no longer match the code, so a
forgotten regeneration is a red build rather than a silently stale port.

## Development

```bash
make dev      # web app dev server on http://localhost:5173/hoermoles-ble/app/
make build    # the static site exactly as GitHub Pages receives it
make test     # every test suite: pytest and vitest
make help     # everything else (lint, format, typecheck, shared, icons, preview, clean)
```

The Makefile only wraps `uv` and `npm`, which stay the source of truth; it
installs dependencies on first use. The equivalents by hand:

```bash
cd python && uv sync --all-packages && uv run pytest
cd spa && npm ci && npx vitest run && npm run dev
```

`pre-commit install` wires up ruff, ESLint/Prettier and the shared-artifact
check. The ESLint/Prettier hooks call the project's own npm scripts, so
`cd spa && npm ci` has to have run at least once.

Web Bluetooth needs a secure context, which `localhost` counts as - so the dev
server works without TLS. On Linux, Chrome additionally needs
`chrome://flags/#enable-experimental-web-platform-features` before it will
expose any Bluetooth at all.
