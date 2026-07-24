<script lang="ts">
  import { PREFIX_ENCRYPTED, type StoredCredential } from 'hoermoles-ble-js';

  import { displayName, exportBundleJson, exportBundleText, isExportable } from '../lib/drives.svelte';
  import QrDisplay from './QrDisplay.svelte';

  interface Props {
    drives: StoredCredential[];
  }

  const { drives }: Props = $props();

  let passphrase = $state('');
  let confirmation = $state('');
  let encrypt = $state(true);
  let output = $state<string | null>(null);
  let showQr = $state(false);
  let feedback = $state<string | null>(null);
  let error = $state<string | null>(null);

  const exportable = $derived(drives.filter(isExportable));
  const blocked = $derived(drives.filter((drive) => !isExportable(drive)));

  // A shareable link is only offered for the encrypted form. The credential
  // rides in the URL's # fragment, which is never sent to a server (see below),
  // but it does persist in browser history, the clipboard, and chat-app link
  // previews - so an unencrypted one would scatter a plaintext root key. This
  // mirrors the deep-link policy in SPA_PLAN.md.
  const shareLink = $derived.by(() => {
    if (!output || !output.startsWith(PREFIX_ENCRYPTED)) return null;
    // The app's own URL, minus any existing hash/query and a trailing
    // index.html, so the link works wherever the app is hosted.
    const base = (location.origin + location.pathname).replace(/index\.html$/, '');
    // The bundle is embedded verbatim, NOT through encodeURIComponent: it is
    // already base64url (URL-fragment-safe by construction, see bundle.ts), and
    // percent-encoding the "HMOLES1E:" prefix's colon would break the plain-text
    // consumers - `hoermoles-ble import "<link>"` splits on "#import=" without
    // URL-decoding and would then reject the mangled prefix (verified). The
    // in-app receiver (App.svelte) runs decodeURIComponent, which is a harmless
    // no-op on this alphabet.
    return `${base}#import=${output}`;
  });

  const canNativeShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  function resetOutput() {
    output = null;
    showQr = false;
    feedback = null;
  }

  async function exportText() {
    error = null;
    feedback = null;
    output = null;
    showQr = false;
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

  async function copyText(value: string | null, label: string) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      feedback = `${label} copied to the clipboard.`;
    } catch {
      feedback = `Could not access the clipboard - select the text and copy it manually.`;
    }
  }

  async function shareViaSheet() {
    if (!shareLink) return;
    try {
      await navigator.share({
        title: 'Hoermoles drive',
        text: 'Open this in Hoermoles to add the drive (you will need the passphrase).',
        url: shareLink,
      });
    } catch {
      // The user dismissing the share sheet also rejects - not an error worth showing.
    }
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
        <input type="checkbox" bind:checked={encrypt} onchange={resetOutput} />
        Encrypt with a passphrase
      </label>

      {#if encrypt}
        <label for="export-pass">Passphrase</label>
        <input id="export-pass" type="password" bind:value={passphrase} autocomplete="new-password" />
        <label for="export-pass2">Repeat passphrase</label>
        <input id="export-pass2" type="password" bind:value={confirmation} autocomplete="new-password" />
      {:else}
        <div class="notice danger">
          Without a passphrase this <em>is</em> the key to your garage. Anyone who photographs the QR code,
          or finds the text in a chat or browser history, can open the door.
        </div>
      {/if}

      <div class="row" style="margin-top: 0.75rem">
        <button class="primary" onclick={exportText}>Export</button>
        <button onclick={downloadJson}>Download JSON file</button>
      </div>
    {/if}

    {#if output}
      <div class="row" style="margin-top: 1rem">
        <button onclick={() => copyText(output, 'Export code')}>Copy code</button>
        <button aria-pressed={showQr} onclick={() => (showQr = !showQr)}>
          {showQr ? 'Hide QR code' : 'Show QR code'}
        </button>
        <button onclick={resetOutput}>Hide</button>
      </div>

      {#if showQr}
        <p class="muted" style="margin-top: 0.75rem">
          Scan this from another phone's <strong>Add</strong> tab. Hold it steady and fill the frame.
        </p>
        <div style="display: flex; justify-content: center; margin: 0.5rem 0">
          <QrDisplay text={output} />
        </div>
      {/if}

      <label for="export-output">Export code</label>
      <textarea id="export-output" readonly value={output}></textarea>
      <p class="muted">
        Import it with <code>hoermoles-ble import "&lt;code&gt;"</code>, or paste it into this app on
        another device.
      </p>

      {#if shareLink}
        <p style="font-weight: 600; margin: 0.75rem 0 0.25rem">Shareable link</p>
        <p class="muted">
          Opens the app with this drive filled in. The credential travels in the link's
          <code>#</code> fragment, which browsers never send to any server - GitHub Pages only ever sees the
          plain app. It does stay in history and messages, though, which is why links are offered for the encrypted
          export only. The recipient still needs the passphrase.
        </p>
        <div class="row">
          <button class="primary" onclick={() => copyText(shareLink, 'Link')}>Copy link</button>
          {#if canNativeShare}
            <button onclick={shareViaSheet}>Share…</button>
          {/if}
        </div>
      {:else}
        <p class="muted">
          Turn on encryption and export again to also get a shareable link - unencrypted links are
          withheld on purpose, since a link lingers in history and chat previews.
        </p>
      {/if}

      {#if feedback}
        <div class="notice success">{feedback}</div>
      {/if}
    {/if}

    {#if error}
      <div class="notice danger">{error}</div>
    {/if}
  {/if}
</div>
