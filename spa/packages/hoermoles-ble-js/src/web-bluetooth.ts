/**
 * Web Bluetooth implementation of {@link BleTransport}.
 *
 * Things that differ from the bleak-based Python transport and matter:
 *
 * - **Writes are serialised through the browser process.** Every `writeValue*`
 *   is an IPC round trip, so a loop of 20-byte chunks is meaningfully slower
 *   here than in bleak. The drive appears to allow only ~100-150 ms between the
 *   first chunk and the end of a frame before it drops the link, so this is the
 *   single riskiest part of the whole web port. `write()` therefore does the
 *   minimum possible work per chunk and never awaits anything else in between.
 * - **`writeValueWithoutResponse()`** is the equivalent of bleak's
 *   `write_gatt_char(..., response=False)` - it does not wait for an ATT
 *   acknowledgement per chunk and is the faster of the two. We fall back to
 *   `writeValueWithResponse()` only if the characteristic does not advertise
 *   the writeWithoutResponse property.
 * - **No MTU is exposed.** Chunking stays at the protocol's 20 bytes.
 * - **No advertisement data.** `watchAdvertisements()` is behind an experimental
 *   flag in every current Chrome, so nothing equivalent to `advertisement.py`
 *   is possible here for normal users. See `deviceCapabilities()`.
 */

import { BC_RX, BC_SERVICE, BC_TX } from './protocol.js';
import type { BleTransport, LogFn } from './transport.js';

export class WebBluetoothUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WebBluetoothUnavailableError';
  }
}

export function isWebBluetoothAvailable(): boolean {
  return typeof navigator !== 'undefined' && navigator.bluetooth !== undefined;
}

/**
 * What this browser will actually let us do. The UI uses this to offer the
 * one-tap path only where it exists, instead of promising it everywhere and
 * failing on most devices.
 */
export interface BluetoothCapabilities {
  available: boolean;
  /** `getDevices()` - remembering a permitted device across page loads.
   * Experimental-flag gated in current Chrome. */
  canRememberDevices: boolean;
  /** `watchAdvertisements()` - reading status without connecting.
   * Experimental-flag gated in current Chrome. */
  canWatchAdvertisements: boolean;
  secureContext: boolean;
}

export function deviceCapabilities(): BluetoothCapabilities {
  const available = isWebBluetoothAvailable();
  // `BluetoothDevice` is a type-only declaration in @types/web-bluetooth, so it
  // has to be reached through globalThis to be inspected at runtime.
  const devicePrototype = (globalThis as { BluetoothDevice?: { prototype?: Record<string, unknown> } })
    .BluetoothDevice?.prototype;

  return {
    available,
    canRememberDevices: available && typeof navigator.bluetooth.getDevices === 'function',
    canWatchAdvertisements: available && typeof devicePrototype?.watchAdvertisements === 'function',
    secureContext: typeof window !== 'undefined' ? window.isSecureContext : false,
  };
}

/** Opens the browser's device chooser. Must be called from a user gesture -
 * calling it from a timer or a resumed promise throws `NotAllowedError`. */
export async function requestDrive(): Promise<BluetoothDevice> {
  if (!isWebBluetoothAvailable()) {
    throw new WebBluetoothUnavailableError(
      'This browser has no Web Bluetooth. Use Chrome or Edge on Android, Windows, macOS or ChromeOS ' +
        '(on Linux, enable chrome://flags/#enable-experimental-web-platform-features). ' +
        'Safari and Firefox do not implement it at all.',
    );
  }
  return navigator.bluetooth.requestDevice({
    filters: [{ services: [BC_SERVICE] }],
    // Required even though the service is already in `filters` - without it,
    // getPrimaryService() throws SecurityError.
    optionalServices: [BC_SERVICE],
  });
}

/** Previously permitted drives, when the browser supports it. Returns an empty
 * list rather than throwing where it does not, so callers can treat "no
 * remembered devices" and "cannot remember devices" the same way. */
export async function rememberedDrives(): Promise<BluetoothDevice[]> {
  if (!deviceCapabilities().canRememberDevices) return [];
  try {
    return await navigator.bluetooth.getDevices();
  } catch {
    return [];
  }
}

export class WebBluetoothTransport implements BleTransport {
  private readonly device: BluetoothDevice;
  private readonly onLog: LogFn;
  private tx: BluetoothRemoteGATTCharacteristic | null = null;
  private rx: BluetoothRemoteGATTCharacteristic | null = null;
  private notifyListener: ((event: Event) => void) | null = null;
  private writeWithoutResponse = true;

  constructor(device: BluetoothDevice, onLog: LogFn = () => {}) {
    this.device = device;
    this.onLog = onLog;
  }

  get name(): string {
    return this.device.name ?? this.device.id;
  }

  async connect(): Promise<void> {
    if (!this.device.gatt) throw new Error('Device exposes no GATT server');
    const server = await this.device.gatt.connect();
    const service = await server.getPrimaryService(BC_SERVICE);
    this.tx = await service.getCharacteristic(BC_TX);
    this.rx = await service.getCharacteristic(BC_RX);
    this.writeWithoutResponse = this.tx.properties.writeWithoutResponse;
    this.onLog(
      `Connected to ${this.name} (writes: ${this.writeWithoutResponse ? 'withoutResponse' : 'withResponse'})`,
    );
  }

  async disconnect(): Promise<void> {
    // Best effort: the link is frequently gone already by the time we get here
    // (the drive hangs up on its own after a command).
    try {
      this.device.gatt?.disconnect();
    } catch (error) {
      this.onLog(`Disconnect failed, connection was likely already gone (${String(error)})`);
    }
    this.tx = null;
    this.rx = null;
  }

  async write(data: Uint8Array): Promise<void> {
    if (!this.tx) throw new Error('not connected');
    if (this.writeWithoutResponse) {
      await this.tx.writeValueWithoutResponse(data as BufferSource);
    } else {
      await this.tx.writeValueWithResponse(data as BufferSource);
    }
  }

  async startNotify(callback: (data: Uint8Array) => void): Promise<void> {
    if (!this.rx) throw new Error('not connected');
    this.notifyListener = (event: Event) => {
      const characteristic = event.target as BluetoothRemoteGATTCharacteristic;
      const value = characteristic.value;
      if (!value) return;
      callback(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    };
    this.rx.addEventListener('characteristicvaluechanged', this.notifyListener);
    await this.rx.startNotifications();
  }

  async stopNotify(): Promise<void> {
    if (!this.rx) return;
    if (this.notifyListener) {
      this.rx.removeEventListener('characteristicvaluechanged', this.notifyListener);
      this.notifyListener = null;
    }
    try {
      await this.rx.stopNotifications();
    } catch (error) {
      this.onLog(`stopNotifications failed during cleanup (${String(error)})`);
    }
  }

  onDisconnected(handler: () => void): () => void {
    const listener = () => handler();
    this.device.addEventListener('gattserverdisconnected', listener);
    return () => this.device.removeEventListener('gattserverdisconnected', listener);
  }
}
