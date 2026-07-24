/**
 * Transport abstraction, mirroring `hoermoles_ble.transport.BleTransport`.
 *
 * The client talks only to this interface, so the protocol logic can be tested
 * against a fake without a browser or a radio, and a future non-Web-Bluetooth
 * backend (a native wrapper, a bridge) slots in without touching `client.ts`.
 */

export interface BleTransport {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  write(data: Uint8Array): Promise<void>;
  startNotify(callback: (data: Uint8Array) => void): Promise<void>;
  stopNotify(): Promise<void>;
}

export type LogFn = (message: string) => void;
