/**
 * Audit-log decoding, verified against the same `log_fields` / `log_timestamps`
 * vectors the Python implementation generates. Because device-log.ts imports the
 * enum name maps straight from shared/device-log.json (guarded by
 * test_interop.py), only the field-decoding *logic* needs checking here - and it
 * is checked byte for byte against the reference.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { fromHex } from '../src/bytes.js';
import {
  decodeLogEntry,
  logTagName,
  logTimestampToDate,
  parseLogFields,
  serviceTypeName,
} from '../src/device-log.js';

interface Vectors {
  log_fields: {
    name: string;
    log_tag: number;
    tag_name: string;
    data: string;
    expected: Record<string, number | string>;
  }[];
  log_timestamps: { wire: number; expected_ms: number }[];
}

const vectorsPath = fileURLToPath(new URL('../../../../shared/test-vectors.json', import.meta.url));
const vectors: Vectors = JSON.parse(readFileSync(vectorsPath, 'utf8'));

/** Compares a decoded field map to the vector's expected map. Time fields are
 * Date objects here and epoch-millisecond numbers in the vector. */
function expectFieldsMatch(
  actual: Record<string, number | string | Date>,
  expected: Record<string, number | string>,
): void {
  expect(Object.keys(actual).sort()).toEqual(Object.keys(expected).sort());
  for (const [key, want] of Object.entries(expected)) {
    const got = actual[key];
    if (got instanceof Date) {
      expect(got.getTime()).toBe(want);
    } else {
      expect(got).toBe(want);
    }
  }
}

describe('parseLogFields matches the Python reference', () => {
  for (const vector of vectors.log_fields) {
    it(vector.name, () => {
      expect(logTagName(vector.log_tag)).toBe(vector.tag_name);
      const fields = parseLogFields(vector.log_tag, fromHex(vector.data));
      expectFieldsMatch(fields, vector.expected);
    });
  }
});

describe('logTimestampToDate matches the Python reference', () => {
  for (const { wire, expected_ms } of vectors.log_timestamps) {
    it(`wire ${wire}`, () => {
      expect(logTimestampToDate(wire).getTime()).toBe(expected_ms);
    });
  }

  it('uses the 2000-01-01 epoch, not the Unix epoch', () => {
    expect(logTimestampToDate(0).toISOString()).toBe('2000-01-01T00:00:00.000Z');
  });
});

describe('name lookups', () => {
  it('resolves a known log tag and falls back for an unknown one', () => {
    expect(logTagName(1)).toBe('REGISTER_ROOT');
    expect(logTagName(250)).toBe('unknown log tag 250');
  });

  it('resolves a known service type and falls back for an unknown one', () => {
    expect(serviceTypeName(1)).toBe('Betriebsstunden');
    expect(serviceTypeName(250)).toBe('unknown service type 250');
  });
});

describe('decodeLogEntry', () => {
  it('bundles tag name, timestamp and parsed fields', () => {
    // REGISTER_ROOT with causing_admin_id=5, timestamp = 1,000,000 s past 2000.
    const decoded = decodeLogEntry({ logTag: 1, timestampRaw: 1_000_000, data: fromHex('0500') });
    expect(decoded.tagName).toBe('REGISTER_ROOT');
    expect(decoded.timestamp.getTime()).toBe((946684800 + 1_000_000) * 1000);
    expect(decoded.fields.causing_admin_id).toBe(5);
  });

  it('returns empty fields for an unrecognised tag', () => {
    expect(parseLogFields(99, fromHex('deadbeef'))).toEqual({});
  });
});
