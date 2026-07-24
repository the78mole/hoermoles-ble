<script lang="ts">
  import type { StoredCredential } from 'hoermoles-ble-js';

  import { displayName, exportBundleJson, exportBundleText, isExportable } from '../lib/drives.svelte';

  interface Props {
    drives: StoredCredential[];
  }

  const { drives }: Props = $props();

  let passphrase = $state('');
  let confirmation = $state('');
  let encrypt = $state(true);
  let output = $state<string | null>(null);
  let error = $state<string | null>(null);

  const exportable = $derived(drives.filter(isExportable));
  const blocked = $derived(drives.filter((drive) => !isExportable(drive)));

  async function exportText() {
    error = null;
    output = null;
    if (encrypt) {
      if (passphrase === '') {
        error = 'Enter a passphrase, or turn encryption off deliberately.';
        return;
      }
      if (passphrase !== confirmation) {
        error = 'The passphrases do not match.';
        return;
      }
    }
    try {
      output = await exportBundleText(exportable, encrypt ? passphrase : undefined);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
    }
  }

  async function downloadJson() {
    error = null;
    try {
      const json = await exportBundleJson(exportable);
      // Blob URL, not a data: URL - the CSP allows blob: for exactly this, and
      // nothing here ever touches the network.
      const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'hoermoles-credentials.json';
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
    }
  }

  async function copyOutput() {
    if (output) await navigator.clipboard.writeText(output);
  }
</script>

<div class="card">
  <h2>Export credentials</h2>

  {#if drives.length === 0}
    <p class="muted">No credentials stored yet.</p>
  {:else}
    <p class="muted">
      Produces the same format <code>hoermoles-ble import</code> reads, so a drive registered here can be used
      from the CLI and from other devices.
    </p>

    {#if blocked.length > 0}
      <div class="notice warning">
        {blocked.length} credential{blocked.length === 1 ? '' : 's'} cannot be exported, because
        {blocked.length === 1 ? 'it was' : 'they were'} stored without the re-export option:
        {blocked.map(displayName).join(', ')}. That is working as intended - the key was made unreadable
        on purpose. Re-import from your original backup to change it.
      </div>
    {/if}

    {#if exportable.length > 0}
      <label class="inline">
        <input type="checkbox" bind:checked={encrypt} />
        Encrypt with a passphrase
      </label>

      {#if encrypt}
        <label for="export-pass">Passphrase</label>
        <input id="export-pass" type="password" bind:value={passphrase} autocomplete="new-password" />
        <label for="export-pass2">Repeat passphrase</label>
        <input id="export-pass2" type="password" bind:value={confirmation} autocomplete="new-password" />
      {:else}
        <div class="notice danger">
          Without a passphrase this text <em>is</em> the key to your garage. Anyone who photographs it, or
          finds it in a chat or browser history, can open the door.
        </div>
      {/if}

      <div class="row" style="margin-top: 0.75rem">
        <button class="primary" onclick={exportText}>Show export code</button>
        <button onclick={downloadJson}>Download JSON file</button>
      </div>
    {/if}

    {#if output}
      <label for="export-output">Export code</label>
      <textarea id="export-output" readonly value={output}></textarea>
      <div class="row">
        <button onclick={copyOutput}>Copy to clipboard</button>
        <button onclick={() => (output = null)}>Hide</button>
      </div>
      <p class="muted">
        Import it with <code>hoermoles-ble import "&lt;code&gt;"</code>, or paste it into this app on
        another device.
      </p>
    {/if}

    {#if error}
      <div class="notice danger">{error}</div>
    {/if}
  {/if}
</div>
