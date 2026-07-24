/**
 * Connection lifecycle, kept out of the components.
 *
 * The awkward part this exists to hide: Web Bluetooth cannot silently reconnect
 * to a device across page loads unless the browser has `getDevices()` enabled
 * (experimental flag in every current Chrome). So the honest model is a
 * *session*: the user picks the drive once from the browser chooser, we hold on
 * to that `BluetoothDevice` object for as long as the page lives, and reconnect
 * to it without a new chooser as often as needed.
 *
 * The drive itself also hangs up on its own a moment after each command, so
 * "connected" is never a steady state. Every action therefore connects,
 * does its thing, and lets go - `withConnection()` is that pattern.
 */

import {
  HoermannClient,
  WebBluetoothTransport,
  rememberedDrives,
  requestDrive,
  type DriveCredentials,
} from 'hoermoles-ble-js';

export type LogLevel = 'info' | 'warn' | 'error';

export interface LogLine {
  at: Date;
  level: LogLevel;
  message: string;
}

/* eslint-disable svelte/prefer-svelte-reactivity --
 * SvelteMap/SvelteDate exist so that mutations drive re-renders. Neither
 * applies here: `picked` is a plain lookup that is only ever read on demand
 * inside an async function, and a log line's timestamp is written once and
 * never mutated. Reactive wrappers would add allocation and indirection for a
 * reactivity nobody subscribes to. Only the `log` rune below is reactive, and
 * it is replaced wholesale rather than mutated in place.
 */

/** Devices the user has picked this session, keyed by the browser's device id. */
const picked = new Map<string, BluetoothDevice>();

export const log = $state<{ lines: LogLine[] }>({ lines: [] });

export function addLog(message: string, level: LogLevel = 'info'): void {
  log.lines = [...log.lines.slice(-199), { at: new Date(), level, message }];
}

export function clearLog(): void {
  log.lines = [];
}

/** Opens the browser chooser. Must be called straight from a click handler -
 * Web Bluetooth rejects it otherwise. */
export async function pickDrive(): Promise<BluetoothDevice> {
  const device = await requestDrive();
  picked.set(device.id, device);
  addLog(`Selected ${device.name ?? device.id}`);
  return device;
}

/** Everything we can talk to without opening the chooser again: this session's
 * picks plus, where the browser allows it, previously permitted devices. */
export async function availableDrives(): Promise<BluetoothDevice[]> {
  const remembered = await rememberedDrives();
  const byId = new Map(picked);
  for (const device of remembered) byId.set(device.id, device);
  return [...byId.values()];
}

/**
 * Connects, runs `action`, and always disconnects again.
 *
 * The initial `waitForAnyNotification()` is not optional: every signed command
 * is HMACed over a challenge that only arrives with the drive's first
 * notification. Sending before it lands means signing against an all-zero
 * challenge, which the drive rejects.
 */
export async function withConnection<T>(
  device: BluetoothDevice,
  action: (client: HoermannClient) => Promise<T>,
): Promise<T> {
  const transport = new WebBluetoothTransport(device, (message) => addLog(message));
  const client = new HoermannClient(transport, (message) => addLog(message));
  await client.open();
  try {
    try {
      await client.waitForAnyNotification(10_000);
    } catch {
      addLog('No initial notification - the challenge may be stale, trying anyway', 'warn');
    }
    return await action(client);
  } finally {
    try {
      await client.close();
    } catch (error) {
      addLog(`Cleanup after disconnect failed: ${String(error)}`, 'warn');
    }
  }
}

/** Triggers a channel on a drive. */
export async function sendChannel(
  device: BluetoothDevice,
  credentials: DriveCredentials,
  channel: number,
): Promise<void> {
  await withConnection(device, async (client) => {
    await client.openChannel(credentials, channel);
    // The drive answers with a status notification; missing it is not an error,
    // it usually just means it hung up first.
    try {
      await client.waitForAnyNotification(5000);
    } catch {
      /* expected often enough not to be worth reporting */
    }
  });
}
