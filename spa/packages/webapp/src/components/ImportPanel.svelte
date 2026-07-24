<script lang="ts">
  import { isEncryptedBundle } from 'hoermoles-ble-js';
  import { untrack } from 'svelte';

  import { importBundle } from '../lib/drives.svelte';
  import QrCapture from './QrCapture.svelte';

  interface Props {
    oncomplete?: () => void;
    /** Bundle text taken from an `#import=` link, filled in on first render. */
    prefill?: string;
  }

  const { oncomplete, prefill = '' }: Props = $props();

  // Seed once and then let the field be the source of truth - `prefill` comes
  // from a URL fragment read at startup and never changes afterwards, so
  // untrack() states that intent instead of leaving a reactivity warning.
  let text = $state(untrack(() => prefill));
  let passphrase = $state('');
  let allowReexport = $state(false);
  let busy = $state(false);
  let result = $state<{ kind: 'success' | 'danger'; message: string } | null>(null);

  const needsPassphrase = $derived(text.trim() !== '' && isEncryptedBundle(text));

  async function readFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) text = await file.text();
    input.value = '';
  }

  async function submit() {
    busy = true;
    result = null;
    try {
      const saved = await importBundle(text, {
        passphrase: needsPassphrase ? passphrase : undefined,
        allowReexport,
      });
      result = {
        kind: 'success',
        message: `Imported ${saved.length} credential${saved.length === 1 ? '' : 's'}: ${saved
          .map((entry) => entry.deviceAddress)
          .join(', ')}`,
      };
      text = '';
      passphrase = '';
      oncomplete?.();
    } catch (error) {
      result = { kind: 'danger', message: error instanceof Error ? error.message : String(error) };
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2>Import from the CLI</h2>
  <p class="muted">
    Run <code>hoermoles-ble export</code> on the machine that registered the drive. It prints a QR code;
    <code>--encrypt</code>
    protects it with a passphrase, <code>--out</code> writes a JSON file instead.
  </p>

  <QrCapture label="Scan the export QR code" onresult={(scanned) => (text = scanned)} />

  <label for="import-file">Or load a JSON file</label>
  <input id="import-file" type="file" accept="application/json,.json,.txt" onchange={readFile} />

  <label for="import-text">Or paste the code</label>
  <textarea
    id="import-text"
    bind:value={text}
    placeholder="HMOLES1:… / HMOLES1E:… / an import link / the JSON file contents"></textarea>

  {#if needsPassphrase}
    <label for="import-pass">Passphrase</label>
    <input id="import-pass" type="password" bind:value={passphrase} autocomplete="off" />
  {/if}

  <label class="inline">
    <input type="checkbox" bind:checked={allowReexport} />
    Allow exporting this credential again from this device
  </label>
  <p class="muted">
    Leave this off unless you need it. With it off, the root key is stored so that not even this app can
    read it back - it can sign door commands but can never be copied out again. With it on, a readable
    copy is kept.
  </p>

  <button class="primary" disabled={busy || text.trim() === ''} onclick={submit}>
    {busy ? 'Importing…' : 'Import'}
  </button>

  {#if result}
    <div class="notice {result.kind}">{result.message}</div>
  {/if}
</div>
