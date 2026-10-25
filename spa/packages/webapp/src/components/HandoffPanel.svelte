<script lang="ts">
  import { encryptHandoff, handoffDeliveryUrl, type HandoffRequest } from 'hoermoles-ble-js';

  import { displayName, drives, exportBundleText, isExportable } from '../lib/drives.svelte';
  import { addLog } from '../lib/session.svelte';

  interface Props {
    request: HandoffRequest;
    onclose: () => void;
  }

  const { request, onclose }: Props = $props();

  let busy = $state(false);
  let sentUrl = $state<string | null>(null);
  let error = $state<string | null>(null);

  // HA rejects a bundle without this drive, so there is nothing to choose: it
  // is this drive or nothing.
  const drive = $derived(
    drives.items.find((record) => record.deviceAddress.toUpperCase() === request.address) ?? null,
  );

  async function send() {
    if (!drive) return;
    busy = true;
    error = null;
    try {
      // Plaintext bundle on purpose: the envelope already encrypts it to a key
      // that only this one HA config flow holds, and a passphrase would just be
      // one more thing to type into HA.
      const envelope = await encryptHandoff(request, await exportBundleText([drive]));
      sentUrl = handoffDeliveryUrl(request, envelope);
      // A top-level navigation, not a fetch: the CSP's connect-src 'none' stays
      // intact. A new tab keeps this app where it is.
      window.open(sentUrl, '_blank', 'noopener,noreferrer');
      addLog(`Key for ${request.address} handed to Home Assistant at ${request.host}.`);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
      addLog(`Handoff to Home Assistant failed: ${error}`, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2>Send a key to Home Assistant</h2>
  <p>
    Home Assistant{#if request.name}&nbsp;<strong>{request.name}</strong>{/if} at
    <code>{request.host}</code> asks for the key of drive <code>{request.address}</code>.
  </p>

  {#if !request.privateHost}
    <div class="notice danger">
      <strong>{request.host} is not a local address.</strong> Only continue if this is your own Home Assistant
      and you just opened its setup dialog. A QR code someone else put in front of you would send the key to
      your garage to them.
    </div>
  {/if}

  {#if !request.secure}
    <p class="muted">
      Plain <code>http://</code> is fine here: the key is encrypted for this one setup dialog in Home Assistant,
      and that key disappears when the dialog closes.
    </p>
  {/if}

  {#if !drives.loaded}
    <p class="muted">Loading credentials…</p>
  {:else if !drive}
    <div class="notice warning">
      This app has no key for <code>{request.address}</code>. Import or register the drive here first, or
      paste an export from the CLI into Home Assistant instead.
    </div>
  {:else if !isExportable(drive)}
    <div class="notice warning">
      <strong>{displayName(drive)}</strong> was stored without the re-export option, so not even this app can
      read its key back - that is working as intended. Export it from the device or CLI that registered it,
      or re-import your backup here with re-export allowed.
    </div>
  {:else if sentUrl}
    <div class="notice success">
      A new tab with Home Assistant opened and should confirm that the key was received. Go back to the
      Home Assistant setup dialog and press <strong>Submit</strong>.
    </div>
    <p class="muted">
      No tab opened? <a href={sentUrl} target="_blank" rel="noopener noreferrer">Open it here</a>.
    </p>
  {:else}
    <p>
      Send the key of <strong>{displayName(drive)}</strong>? Home Assistant can then open this garage
      door whenever it wants.
    </p>
    <div class="row">
      <button class="primary" disabled={busy} onclick={send}>
        {busy ? 'Encrypting…' : 'Send key to Home Assistant'}
      </button>
    </div>
  {/if}

  {#if error}
    <div class="notice danger">{error}</div>
  {/if}

  <div class="row" style="margin-top: 0.75rem">
    <button onclick={onclose}>{sentUrl ? 'Done' : 'Cancel'}</button>
  </div>
</div>
