/**
 * Credential bundles, in two halves:
 *
 * 1. Cross-language: decode bundles the Python CLI actually produced (pinned in
 *    `shared/test-vectors.json`). This is what proves `hoermoles-ble export` ->
 *    web app works, without needing both runtimes in one test.
 * 2. Local round trips and the error paths, which have no Python counterpart.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { toHex } from '../src/bytes.js';
import {
  BundleError,
  PREFIX_ENCRYPTED,
  PREFIX_PLAIN,
  bundleFromJson,
  bundleToJson,
  decodeBundle,
  encodeBundle,
  isEncryptedBundle,
  type BundleEntry,
} from '../src/bundle.js';

interface BundleVectors {
  expected: {
    device_address: string;
    root_id: number;
    root_key: string;
    qr_prefix: string;
    created_unix: number;
    product_class: number;
    product_id: number;
    product_name: string;
    serial_no: string;
  };
  plain_text: string;
  json_file: string;
  encrypted: { passphrase: string; text: string };
}

const vectorsPath = fileURLToPath(new URL('../../../../shared/test-vectors.json', import.meta.url));
const bundles: BundleVectors = JSON.parse(readFileSync(vectorsPath, 'utf8')).bundles;

function expectMatchesVector(entry: BundleEntry): void {
  const expected = bundles.expected;
  expect(entry.deviceAddress).toBe(expected.device_address);
  expect(entry.rootId).toBe(expected.root_id);
  expect(toHex(entry.rootKey)).toBe(expected.root_key);
  expect(entry.qrPrefix).toBe(expected.qr_prefix);
  expect(entry.createdUnix).toBe(expected.created_unix);
  expect(entry.productClass).toBe(expected.product_class);
  expect(entry.productId).toBe(expected.product_id);
  expect(entry.productName).toBe(expected.product_name);
  expect(entry.serialNo).toBe(expected.serial_no);
}

describe('bundles produced by the Python CLI', () => {
  it('decodes the plaintext text form', async () => {
    const [entry] = await decodeBundle(bundles.plain_text);
    expectMatchesVector(entry);
  });

  it('decodes the JSON file form', async () => {
    const [entry] = await decodeBundle(bundles.json_file);
    expectMatchesVector(entry);
  });

  it('decodes the passphrase-encrypted form', async () => {
    const [entry] = await decodeBundle(bundles.encrypted.text, bundles.encrypted.passphrase);
    expectMatchesVector(entry);
  });

  it('preserves the uint64 serial number exactly', async () => {
    // 302626026414510307 > Number.MAX_SAFE_INTEGER - a JSON number would round
    // this, which is why the wire format uses a string.
    const [entry] = await decodeBundle(bundles.plain_text);
    expect(entry.serialNo).toBe('302626026414510307');
    expect(BigInt(entry.serialNo!)).toBe(302626026414510307n);

    // And this is what would have happened as a JSON number: note the literal
    // below cannot even be written faithfully in JS source, which is the point.
    expect(Number(entry.serialNo) > Number.MAX_SAFE_INTEGER).toBe(true);
    expect(String(Number(entry.serialNo))).not.toBe(entry.serialNo);
  });

  it('refuses the encrypted form with the wrong passphrase', async () => {
    await expect(decodeBundle(bundles.encrypted.text, 'wrong')).rejects.toThrow(/wrong passphrase/);
  });

  it('refuses the encrypted form without a passphrase', async () => {
    await expect(decodeBundle(bundles.encrypted.text)).rejects.toThrow(/passphrase is required/);
  });
});

describe('local round trips', () => {
  const entry: BundleEntry = {
    deviceAddress: 'AA:BB:CC:DD:EE:FF',
    rootId: 7,
    rootKey: new Uint8Array(32).fill(0xab),
    qrPrefix: '',
    createdUnix: 1700000000,
  };

  it('plaintext text form', async () => {
    const text = await encodeBundle([entry]);
    expect(text.startsWith(PREFIX_PLAIN)).toBe(true);
    expect(isEncryptedBundle(text)).toBe(false);

    const [restored] = await decodeBundle(text);
    expect(restored.rootId).toBe(7);
    expect(toHex(restored.rootKey)).toBe(toHex(entry.rootKey));
    expect(restored.productClass).toBeUndefined();
  });

  it('encrypted text form', async () => {
    const text = await encodeBundle([entry], 'pw');
    expect(text.startsWith(PREFIX_ENCRYPTED)).toBe(true);
    expect(isEncryptedBundle(text)).toBe(true);

    const [restored] = await decodeBundle(text, 'pw');
    expect(toHex(restored.rootKey)).toBe(toHex(entry.rootKey));
  });

  it('encryption is randomized', async () => {
    expect(await encodeBundle([entry], 'pw')).not.toBe(await encodeBundle([entry], 'pw'));
  });

  it('text form is safe inside a URL fragment', async () => {
    const payload = (await encodeBundle([entry])).slice(PREFIX_PLAIN.length);
    expect(payload).not.toMatch(/[+/=]/);
  });

  it('accepts a full import URL', async () => {
    const text = await encodeBundle([entry]);
    const [restored] = await decodeBundle(`https://the78mole.github.io/hoermoles-ble/#import=${text}`);
    expect(restored.rootId).toBe(7);
  });

  it('JSON file form', async () => {
    const [restored] = bundleFromJson(bundleToJson([entry]));
    expect(restored.rootId).toBe(7);
  });

  it('carries several drives in one bundle', async () => {
    const second: BundleEntry = { ...entry, deviceAddress: 'F1:26:AF:CC:41:86', rootId: 1 };
    const restored = await decodeBundle(await encodeBundle([entry, second]));
    expect(restored.map((e) => e.rootId)).toEqual([7, 1]);
  });

  it('accepts a legacy numeric serial number', async () => {
    const legacy = JSON.stringify({
      format: 'hoermoles-credentials',
      v: 1,
      devices: [
        {
          device_address: 'AA:BB:CC:DD:EE:FF',
          root_id: 1,
          root_key_hex: '00'.repeat(32),
          product_class: 2,
          product_id: 2,
          serial_no: 12345,
        },
      ],
    });
    const [restored] = await decodeBundle(legacy);
    expect(restored.serialNo).toBe('12345');
  });
});

describe('malformed input', () => {
  it.each([
    ['not a bundle at all', /Unrecognized bundle format/],
    [`${PREFIX_PLAIN}bm90IGpzb24`, /Not valid JSON/],
    ['{"format":"something-else","v":1,"devices":[]}', /Not a hoermoles credential bundle/],
    ['{"format":"hoermoles-credentials","v":99,"devices":[]}', /Unsupported bundle version/],
    ['{"format":"hoermoles-credentials","v":1}', /missing a 'devices' list/],
    ['{"format":"hoermoles-credentials","v":1,"devices":[{"root_id":1}]}', /Malformed bundle entry/],
  ])('rejects %s', async (text, message) => {
    await expect(decodeBundle(text as string)).rejects.toThrow(message as RegExp);
  });

  it('rejects a truncated encrypted envelope', async () => {
    await expect(decodeBundle(`${PREFIX_ENCRYPTED}SE0xRQ`, 'pw')).rejects.toThrow(
      /Malformed encrypted bundle envelope/,
    );
  });

  it('throws BundleError, not a bare Error', async () => {
    await expect(decodeBundle('garbage')).rejects.toBeInstanceOf(BundleError);
  });

  it('rejects an odd-length root key hex', async () => {
    const bad =
      '{"format":"hoermoles-credentials","v":1,"devices":[{"device_address":"A","root_id":1,"root_key_hex":"abc"}]}';
    await expect(decodeBundle(bad)).rejects.toThrow(/Malformed bundle entry/);
  });
});
