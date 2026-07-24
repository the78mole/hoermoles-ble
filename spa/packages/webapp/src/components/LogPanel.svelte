<script lang="ts">
  import { clearLog, log } from '../lib/session.svelte';

  function timestamp(at: Date): string {
    return at.toTimeString().slice(0, 8);
  }
</script>

<div class="card">
  <h2>Connection log</h2>
  <p class="muted">
    Raw protocol traffic and connection events. Worth capturing if something does not work - it shows
    whether the drive answered at all, and with what.
  </p>

  {#if log.lines.length === 0}
    <p class="muted">Nothing logged yet.</p>
  {:else}
    <div class="log">
      {#each log.lines as line (line.at.getTime() + line.message)}
        <div class={line.level}>{timestamp(line.at)} {line.message}</div>
      {/each}
    </div>
    <p style="margin-top: 0.75rem"><button onclick={clearLog}>Clear</button></p>
  {/if}
</div>
