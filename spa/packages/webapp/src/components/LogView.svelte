<script lang="ts">
  import type { DecodedLogEntry, LogFieldValue } from 'hoermoles-ble-js';

  interface Props {
    entries: DecodedLogEntry[];
  }

  const { entries }: Props = $props();

  function formatTime(date: Date): string {
    // Local time, seconds precision - the drive log is minute-to-second granular.
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  function formatValue(value: LogFieldValue): string {
    return value instanceof Date ? formatTime(value) : String(value);
  }

  /** The parsed fields as "key=value" chips, minus the timestamps already shown
   * in their own column. */
  function detailPairs(entry: DecodedLogEntry): [string, string][] {
    return Object.entries(entry.fields)
      .filter(([key]) => key !== 'old_time' && key !== 'new_time')
      .map(([key, value]) => [key, formatValue(value)]);
  }

  function timeChange(entry: DecodedLogEntry): string | null {
    const { old_time: oldTime, new_time: newTime } = entry.fields;
    if (oldTime instanceof Date && newTime instanceof Date) {
      return `${formatTime(oldTime)} → ${formatTime(newTime)}`;
    }
    return null;
  }
</script>

{#if entries.length === 0}
  <p class="muted">The drive reported no log entries.</p>
{:else}
  <div class="log-scroll">
    <table class="log-table">
      <thead>
        <tr>
          <th>When</th>
          <th>Event</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as entry, i (i)}
          <tr>
            <td class="when">{formatTime(entry.timestamp)}</td>
            <td class="event">{entry.tagName}</td>
            <td class="details">
              {#each detailPairs(entry) as [key, value] (key)}
                <span class="chip"><span class="k">{key}</span>{value}</span>
              {/each}
              {#if timeChange(entry)}
                <span class="chip"><span class="k">clock</span>{timeChange(entry)}</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="muted" style="margin-top: 0.5rem">Newest first, as the drive reports them.</p>
{/if}

<style>
  .log-scroll {
    overflow-x: auto;
  }
  .log-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  .log-table th,
  .log-table td {
    text-align: left;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .log-table th {
    color: var(--text-muted);
    font-weight: 600;
    white-space: nowrap;
  }
  .when {
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .event {
    font-weight: 600;
    white-space: nowrap;
  }
  .details {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .chip {
    display: inline-flex;
    align-items: baseline;
    gap: 0.3rem;
    background: var(--surface-raised);
    border-radius: 0.4rem;
    padding: 0.1rem 0.4rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.78rem;
  }
  .chip .k {
    color: var(--text-muted);
  }
</style>
