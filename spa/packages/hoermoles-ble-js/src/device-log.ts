/**
 * Interpretation of the drive's security/access audit log - the TypeScript
 * counterpart of `python/packages/hoermoles-ble/src/hoermoles_ble/device_log.py`.
 *
 * The enum name maps (log tags, device actions, notification types, service
 * types) are not re-typed here: they are imported straight from
 * `shared/device-log.json`, which is generated from device_log.py and guarded
 * by test_interop.py. So there is nothing to keep in sync by hand - change the
 * Python source, regenerate, and this picks it up. The JSON is tiny and gets
 * inlined into the bundle, so there is no runtime fetch (which the CSP forbids
 * anyway).
 *
 * Only the field-decoding *logic* (parseLogFields, timestamp conversion) is
 * ported by hand, and that is byte-verified against the `log_fields` /
 * `log_timestamps` vectors in shared/test-vectors.json. The Python original is
 * the reference for the per-tag byte layouts, including the off-by-one quirks
 * mirrored here deliberately.
 */

import deviceLog from '../../../../shared/device-log.json';
import type { LogEntry } from './protocol.js';

const LOG_TAG_NAMES = deviceLog.log_tag_names as Record<string, string>;
const DEVICE_ACTION_NAMES = deviceLog.device_action_names as Record<string, string>;
const SIGNED_NOTIFICATION_TYPE_NAMES = deviceLog.signed_notification_type_names as Record<
  string,
  string
>;
const SERVICE_TYPE_NAMES = deviceLog.service_type_names as Record<string, string>;
const SERVICE_TYPE_IS_TIMESTAMP = new Set(deviceLog.service_type_is_timestamp);
const LOG_EPOCH_UNIX = deviceLog.log_epoch_unix;

export function logTagName(tag: number): string {
  return LOG_TAG_NAMES[String(tag)] ?? `unknown log tag ${tag}`;
}

export function serviceTypeName(type: number): string {
  return SERVICE_TYPE_NAMES[String(type)] ?? `unknown service type ${type}`;
}

export function isServiceTypeTimestamp(type: number): boolean {
  return SERVICE_TYPE_IS_TIMESTAMP.has(type);
}

/** Log-entry timestamps are seconds since 2000-01-01 UTC (not the Unix epoch);
 * the offset comes from the generated data so it is never hardcoded twice. */
export function logTimestampToDate(wireTimestamp: number): Date {
  return new Date((LOG_EPOCH_UNIX + wireTimestamp) * 1000);
}

/** Little-endian unsigned integer from a 1-4 byte slice - device_log._id. */
function leInt(data: Uint8Array): number {
  let value = 0;
  for (let i = data.length - 1; i >= 0; i--) value = value * 256 + data[i];
  return value;
}

/** device_log._action_name: the 0x100 bit marks "executed by a user/OTK key
 * rather than an admin key" and is stripped before the name lookup. */
function actionName(data: Uint8Array): string {
  const raw = leInt(data);
  const executedByUser = (raw & 0x100) !== 0;
  const name =
    DEVICE_ACTION_NAMES[String(raw & ~0x100)] ?? `UNKNOWN(0x${raw.toString(16).padStart(4, '0')})`;
  return executedByUser ? `${name} (by user/OTK)` : name;
}

function notificationName(data: Uint8Array): string {
  const raw = leInt(data);
  return (
    SIGNED_NOTIFICATION_TYPE_NAMES[String(raw)] ?? `UNKNOWN(0x${raw.toString(16).padStart(4, '0')})`
  );
}

/** A decoded log field: an id (number), a resolved name (string) or a time (Date). */
export type LogFieldValue = number | string | Date;

/**
 * device_log.parse_log_fields: per-LogTag field layout within a log entry's
 * data blob. Mirrors the Python guard conditions and slice ranges exactly
 * (including a couple of apparent off-by-one quirks), returning {} for tags or
 * data it does not recognise rather than guessing.
 */
export function parseLogFields(logTag: number, data: Uint8Array): Record<string, LogFieldValue> {
  const fields: Record<string, LogFieldValue> = {};
  const slice = (start: number, end: number) => leInt(data.subarray(start, end));

  switch (logTag) {
    case 1: // REGISTER_ROOT
      if (data.length >= 2) fields.causing_admin_id = slice(0, 2);
      break;

    case 2: // RELAIS
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length < 4) return fields;
      fields.user_id = slice(2, 3);
      if (data.length >= 4) {
        fields.otk_id = slice(3, 5);
        if (data.length >= 5) fields.toggled_channel = slice(5, 6);
      }
      break;

    case 3: // BLOCKED_ADMIN
      if (data.length >= 4) {
        fields.causing_admin_id = slice(0, 2);
        fields.admin_id = slice(2, 4);
      }
      break;

    case 4: // BLOCKED_USER
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length >= 4) {
        fields.user_id = slice(2, 4);
        if (data.length >= 6) fields.otk_id = slice(4, 6);
      }
      break;

    case 5: // BLOCKED_OTK
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length >= 4) {
        fields.user_id = slice(2, 4);
        if (data.length >= 5) fields.otk_id = slice(4, 5);
      }
      break;

    case 6: // EXECUTED_ADMIN_ACTION
      if (data.length >= 2) {
        fields.causing_admin_id = slice(0, 2);
        if (data.length >= 4) fields.action = actionName(data.subarray(2, 4));
      }
      break;

    case 7: // CLOCKTIME_CHANGED
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length >= 6) {
        fields.old_time = logTimestampToDate(slice(2, 6));
        if (data.length >= 10) fields.new_time = logTimestampToDate(slice(6, 10));
      }
      break;

    case 8: // ACTION_REJECTED
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length < 3) return fields;
      fields.user_id = slice(2, 3);
      if (data.length < 5) return fields;
      fields.otk_id = slice(3, 5);
      if (data.length >= 7) {
        fields.action = actionName(data.subarray(5, 7));
        if (data.length >= 9) fields.notification = notificationName(data.subarray(7, 9));
      }
      break;

    case 9: // IMPULS_WITH_CLOCK
      if (data.length < 2) return fields;
      fields.causing_admin_id = slice(0, 2);
      if (data.length < 3) return fields;
      fields.toggled_channel = slice(2, 3);
      if (data.length >= 7) {
        fields.old_time = logTimestampToDate(slice(3, 7));
        if (data.length >= 11) fields.new_time = logTimestampToDate(slice(7, 11));
      }
      break;
  }
  return fields;
}

/** A fully decoded audit-log entry, ready for display. */
export interface DecodedLogEntry {
  tagName: string;
  timestamp: Date;
  fields: Record<string, LogFieldValue>;
  raw: LogEntry;
}

export function decodeLogEntry(entry: LogEntry): DecodedLogEntry {
  return {
    tagName: logTagName(entry.logTag),
    timestamp: logTimestampToDate(entry.timestampRaw),
    fields: parseLogFields(entry.logTag, entry.data),
    raw: entry,
  };
}
