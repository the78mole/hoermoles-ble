# HA plan: Hoermoles Home Assistant integration

Status: **draft for review - nothing implemented yet.** The package
`python/packages/hoermoles-ble-homeassistant` is still a placeholder (single
`__init__.py` comment, a `pyproject.toml` depending on `hoermoles-ble[bleak]`).

> **No hardware spike has been run for Home Assistant.** The core protocol has
> been verified live against a real Supramatic E4 over a local bleak/BlueZ
> connection, but nothing has yet driven the door through HA's own Bluetooth
> stack - and that stack is exactly where the one real risk lives (section 9,
> risk 1). Do the connection spike before trusting any of the control path.

Goal: a Home Assistant custom component that (a) surfaces a Hoermann BlueSecur
drive's live status **passively, from its BLE advertisement, with no pairing and
no root key**, and (b) triggers channels (open/close/impulse) once a credential
has been imported. Installable via HACS, using HA's shared Bluetooth stack -
never its own scanner or client.

## 0. Decisions proposed for this draft - revise freely

These mirror the shape of the SPA plan's fixed decisions, but here they are
**proposals**, since this is the document you asked to revise first:

- **Two data planes, passive-first.** The advertisement parser
  (`advertisement.py`) already gives position, motion, battery and maintenance
  state without connecting. That becomes the primary entity source. Control
  (channels) is a separate, ephemeral, credential-gated connection. A drive with
  **no** imported credential is still useful - it gets read-only sensors.
- **Use HA's Bluetooth integration, not our own bleak.** The component depends on
  `bluetooth` (manifest dependency) and obtains devices via
  `bluetooth.async_ble_device_from_address` + `bleak-retry-connector`. The core
  `hoermoles-ble` library stays HA-agnostic; the HA-specific glue lives only in
  `custom_components/`.
- **Credential import, not registration, is the primary onboarding.** Reuse the
  `HMOLES1[E]:` bundle format (`bundle.py`) - the user registers once with the
  CLI or SPA, then pastes/imports the bundle into HA. In-HA registration (drive
  in teach mode, paste QR) is offered as an advanced path, not the default.
- **Distribution via HACS as a custom repository**, pulling `hoermoles-ble` from
  PyPI via the manifest `requirements`. Not (yet) aiming for the HA core/default
  HACS store. See section 8 - the monorepo layout needs one decision from you.
- **iot_class: `local_push`.** State is pushed by advertisements; commands are
  local and unauthenticated-to-the-cloud. No polling in the default path.

## 1. What HA's Bluetooth model gives us - and takes away

These drive the design the way the Web Bluetooth constraints drove the SPA.

| Capability | In HA | Consequence for us |
| --- | --- | --- |
| Passive advertisement callbacks | `bluetooth.async_register_callback(match=...)`, shared across all adapters + ESPHome proxies | The **primary** data source - free, connectionless, no root key. Feeds `AdvertisementInfo.from_scan` |
| Two alternating manufacturer packets (6 + 17 bytes) | HA delivers each `BluetoothServiceInfoBleak` as it arrives | Same quirk as the CLI (`advertisement.py` docstring): we must **accumulate** payloads across callbacks, not parse a single one, or every flag comes back falsely `False` |
| Connectable device lookup | `async_ble_device_from_address(hass, addr, connectable=True)` | Needed for control. Returns `None` when only a non-connectable proxy has seen the drive - handle that as "sensors work, control unavailable" |
| Connection establishment | `bleak-retry-connector.establish_connection()` | Replaces our `BleakClient(address)`. Adds retry/backoff and slot management HA needs. **The core lib's `BleakTransport` must accept an injected client** (section 4) |
| ESPHome Bluetooth proxy | connect + write proxied over the network | The timing risk (section 9) is **worse** here: the ~100-150 ms write window may be unmeetable over a proxy round-trip. Local adapter strongly preferred |
| Config-entry storage | `.storage/core.config_entries`, plaintext JSON on disk | The root key is stored like every other HA secret: filesystem-permission protected, **not** encrypted at rest. Say so plainly in the README |
| Discovery | manifest `bluetooth:` matcher (service uuid `669a9001-…` and/or manufacturer id `1972`) | Drives appear as auto-discovered without the user typing a MAC |

## 2. Two data planes

**Passive plane (always on, no credential, no connection).** An
`ActiveBluetoothProcessorCoordinator` (from `habluetooth`) subscribed to the
matcher accumulates the two manufacturer packets per drive and runs
`AdvertisementInfo.from_scan`. Every advertisement refreshes the passive
entities. This is the whole reason the integration is pleasant: door position
and motion update in near-real-time with zero connection cost.

**Control plane (ephemeral, credential-gated).** Channel commands and the
optional menu/log/service reads open a connection, do the one exchange, and
**disconnect immediately** - because the drive tears the link down ~100-150 ms
after the first chunk anyway (see `client.py` `_write_chunked`). We never hold
the GATT connection open. A per-entry `asyncio.Lock` serialises these so two
button presses can't collide on one drive.

The two planes map cleanly onto the library as it stands: passive uses
`advertisement.py` untouched; control uses `HoermannClient` + a transport.

## 3. Entities

Passive (from advertisement - available even with no credential):

- **cover** (`device_class: garage`): position from
  `opening_progress_percent` (product_class 2), motion from `in_action`.
  `open`/`close`/`stop` send a channel command (control plane) - **but** only
  channel 1 "impulse" is verified live, and impulse is a *toggle*, not discrete
  open/close. v1 honest behaviour: all three map to impulse (channel 1), using
  the advertisement position to suppress no-op impulses. Discrete open/close
  (channels 4/5) are unverified - offered only behind an option, off by default,
  labelled as such.
- **binary_sensor**: `moving` (in_action), `low_battery` (device_class
  battery), `maintenance_required` (problem), plus diagnostic ones:
  `protection_active`, `vacation_mode`, `emergency_mode`, `warning_time`,
  `admins_can_be_teached`.
- **sensor**: `position` (%), `rssi` (diagnostic), `product_name`/`serial_no` as
  attributes on the device rather than their own entities.

Control (need a credential + a connectable path):

- **button**: channels 2/3/6 (`light`/`partial`/`ventilation`) - unverified per
  their docstrings, so diagnostic category, disabled by default, name carries the
  "(unverified)" caveat.
- **sensor** (opt-in, off by default): service-data counters (operating hours,
  door cycles, …) via `read_service_data`. This is a *connecting* poll, slow and
  rate-limited (default e.g. every 6 h), never in the hot path. Same treatment
  for a menu/parameter read if wanted later.
- **event** for audit-log entries (`read_log`) - deferred past v1.

Everything unverified against real hardware (`write_properties`, channels 2-6,
open/close) must be visibly marked in the UI, exactly as the SPA plan insists -
we do not present a reverse-engineered guess as if it were confirmed.

## 4. Library changes needed in `hoermoles-ble`

The `BleTransport` ABC is already the seam (four methods; a NimBLE port was the
stated design goal). Two small, testable changes:

1. **Let `BleakTransport` accept an injected `BleakClient`.** Today it builds its
   own `BleakClient(address)` in `connect()`. Add an alternate path -
   `BleakTransport(client=<already-connected-or-connectable>)` or a
   `from_client()` classmethod - so HA can hand it a client from
   `establish_connection()`. Core stays free of `bleak-retry-connector`/
   `habluetooth`; those remain HA-package dependencies only.
2. **Nothing else in core is strictly required.** `advertisement.py`,
   `bundle.py`, `credentials.py`, `client.py`, `menu_settings.py`,
   `device_log.py` are all consumed as-is. If profiling shows we want an
   incremental advertisement accumulator (feed one payload at a time and
   re-derive), that's an additive helper on `AdvertisementInfo`, not a change to
   existing behaviour.

The HA transport wrapper (`custom_components/hoermoles_ble/transport.py`) is
then ~30 lines: `establish_connection` in `connect()`, `write_gatt_char(BC_TX,
…, response=False)`, `start_notify(BC_RX, …)` - reusing `protocol.BC_TX/BC_RX`.

## 5. Config flow

- **Discovery step**: manifest `bluetooth:` matcher surfaces the drive
  automatically; `async_step_bluetooth` shows model + MAC, `unique_id` = MAC.
  Manual `async_step_user` fallback lists drives seen by HA's scanner.
- **Credential step** (menu):
  1. *Paste bundle* - `HMOLES1:` / `HMOLES1E:` string, decoded via `bundle.py`;
     encrypted variant prompts for the passphrase. **Recommended default.**
  2. *Upload/point to a bundle file* - same decoder.
  3. *Register now (advanced)* - assumes the drive is in teach mode
     (`admins_can_be_teached=True`, which the passive plane can confirm and warn
     about); user pastes the QR text; `client.register()` runs and the resulting
     `Credentials` is stored.
  4. *Skip - sensors only* - finish with no credential. Fully supported; the
     cover/buttons simply aren't created until a credential is added later via
     the options flow.
- **Options flow**: enable unverified channels (open/close/2/3/6), enable +
  interval for service-data polling, connection timeout, and "add/replace
  credential" (so a sensors-only entry can be upgraded to control later).

## 6. Coordinator & connection model

- One `ActiveBluetoothProcessorCoordinator` per config entry for the passive
  plane; its `update_method` runs `AdvertisementInfo.from_scan` over the
  accumulated payloads and pushes to entities via the standard
  `PassiveBluetoothDataUpdate`/coordinator dispatch.
- Control is **not** on the coordinator. A small `HoermannConnection` helper owns
  the per-entry lock and does connect→command→disconnect through the injected
  transport. Cover/button entities call it directly; failures raise
  `HomeAssistantError` with an actionable message (e.g. "no connectable path -
  drive only seen via a non-connectable proxy").
- No reconnect loop, no keepalive: the drive doesn't allow it, and holding a slot
  would starve HA's Bluetooth connection pool.

## 7. Secrets

- Root key lives in the config entry's `data`, i.e. `.storage` plaintext -
  standard for HA integrations, but state it in the README rather than imply
  encryption.
- Bundle import means the key is **pasted once**, never re-typed; the encrypted
  bundle variant keeps it ciphertext until it reaches HA.
- No `connect-src`-style exfil channel here (this is server-side Python, not a
  web origin), but the same principle applies: the component makes **zero**
  outbound network calls - worth asserting and testing (no `requirements` that
  phone home; `iot_class: local_push`).

## 8. Packaging, HACS & distribution — decided: its own repository

**Decision:** the integration lives in a **dedicated repository**
(`the78mole/hoermoles-ble-homeassistant`, domain `hoermoles_ble`), depending on
the `hoermoles-ble` core library from **PyPI**. Not inside this monorepo.

Why, in short (full findings in the plan file
`~/.claude/plans/ist-es-m-glich-die-hazy-gizmo.md`):

- HACS only reads `ROOT/custom_components/<domain>/` and downloads those files via
  the GitHub contents API - a **nested** path under `python/packages/…` is
  invisible to it, and a component dir that *is* a symlink won't resolve on
  download. So the component must be real files at a repo root regardless.
- HACS's version picker shows the repo's GitHub **Releases**; in this monorepo the
  `spa/v…` and `python/v…` releases would pollute that list. A dedicated repo
  keeps the picker (and the eventual `hacs/default` submission) clean.
- One integration per repo, a clean `hacs/action` + `hassfest` run, and brands
  registration are all simplest in a repo that contains only the integration.

Consequences for this monorepo:

- The core lib gains an injectable-client `BleakTransport` (§4.1, **done** - see
  `ble_transport.py` + `test_ble_transport.py`) and is published to PyPI; the HA
  repo's `manifest.json` pins that exact version.
- The placeholder package `python/packages/hoermoles-ble-homeassistant/` is
  retired (it has no build purpose once the integration lives elsewhere), leaving
  a pointer to the new repo in `python/README.md`.

In the dedicated repo: `manifest.json` `requirements:
["hoermoles-ble[bleak]==X.Y.Z"]` pins the PyPI release and bumps whenever core
changes; `hacs.json` (`name`, `homeassistant` floor) at repo root; `brand/` icon
plus a `home-assistant/brands` PR; releases via `paulhatch/semantic-version`.

## 9. CI

- **`ha-test.yml`**: `pytest-homeassistant-custom-component`, plus HA's own
  `home-assistant/actions/hassfest` (manifest/strings validation) and the
  `hacs/action` validator. Coverage badge into the same gist as Python/SPA.
- Tests: config-flow (all four credential paths + discovery), passive coordinator
  fed with the **existing** advertisement raw-data test vectors from
  `test_advertisement.py` (the two-packet case), entity state mapping, and the
  control helper with a mocked transport (no real BLE). The chunk/timing risk is
  **not** something CI can cover - only the hardware spike can.
- **Narrow `pypi-publish.yml`'s `paths` first** (the SPA plan already flagged the
  same bug): a new `ha-*.yml` workflow must not trigger a Python release. Scope it
  to `pypi-publish.yml` + `test.yml`, and the HA workflow to
  `paths: ['python/packages/hoermoles-ble-homeassistant/**', 'custom_components/**',
  '.github/workflows/ha-*.yml']`.
- Pre-commit: the component's Python goes through the same ruff hooks.

## 10. Build order

| # | Step | Outcome |
| --- | --- | --- |
| **Spike 1** | On a real HA install with a **local** adapter: `establish_connection` to the drive, push a 49-byte channel frame in three chunks, confirm the impulse fires inside the ~100-150 ms window | Settles whether HA's Bluetooth stack can meet the timing at all. **Do this before building the control plane.** Repeat over an ESPHome proxy to learn if proxies are viable or must be documented as sensors-only |
| 1 | `BleakTransport` accepts an injected client (+ tests) | Core seam ready; no behaviour change for existing callers |
| 2 | Passive plane: coordinator + advertisement accumulation + sensors/binary_sensors/cover-position, **no control yet** | A drive shows live position/motion/battery in HA with zero credentials. Independently valuable and fully testable offline |
| 3 | Config flow: discovery + bundle import + "sensors only" | Onboarding works end-to-end for the passive plane |
| 4 | Control plane: connection helper + cover open/close/stop (impulse) + verified channel 1 | The actual door control, gated behind Spike 1 |
| 5 | HACS packaging (section 8 decision), hassfest/HACS CI, README with the honest security + proxy caveats | Installable |
| 6 | Advanced: in-HA registration, unverified channels behind options, opt-in service-data poll, log `event`s | Feature-complete; each piece clearly marked verified/unverified |

## 11. Risks

1. **The write-timing window - the same one that can sink the SPA, and worse over
   a proxy.** The drive disconnects ~100-150 ms after the first chunk regardless
   of chunk count. HA serialises GATT through `habluetooth`, and an ESPHome proxy
   adds a network round-trip per operation. If a 49-byte / three-write frame
   can't land in time, the control plane is dead over that transport. Local
   adapter is the baseline; proxy support is a spike outcome, not an assumption.
2. **No connectable path.** A drive seen only by a non-connectable proxy gives
   sensors but no control. Handled as a first-class state, not an error.
3. **Unverified protocol paths.** `write_properties`, channels 2-6, and discrete
   open/close are not confirmed against hardware. Same rule as the SPA: never
   present them as verified - diagnostic category, disabled by default, labelled.
4. **Secret at rest.** The root key sits in `.storage` plaintext. This is normal
   for HA but must be stated, not glossed. A host compromise is a door
   compromise.
5. **Release coupling.** The manifest pins a PyPI `hoermoles-ble` version; a
   protocol fix in core needs a core release *and* a manifest bump. Cheap, but a
   step that's easy to forget - CI should assert the pinned version resolves.
