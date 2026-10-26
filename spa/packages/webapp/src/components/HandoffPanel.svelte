<script lang="ts">
  import { encryptHandoff, handoffDeliveryUrl, type HandoffRequest } from 'hoermoles-ble-js';

  import { displayName, drives, exportBundleText, isExportable } from '../lib/drives.svelte';
  import { addLog } from '../lib/session.svelte';

  interface Props {
    request: HandoffRequest;
    onclose: () => void;
  }

  const { request, onclose }: Props = $props();

  let deliveryUrl = $state<string | null>(null);
  let sent = $state(false);
  let error = $state<string | null>(null);

  // HA rejects a bundle without this drive, so there is nothing to choose: it
  // is this drive or nothing.
  const drive = $derived(
    drives.items.find((record) => record.deviceAddress.toUpperCase() === request.address) ?? null,
  );

  // Encrypt up front, so that sending is a plain link the user taps. A tapped
  // link is never pop-up blocked, whereas window.open() after an await is (iOS
  // Safari drops the user activation). Nothing leaves the phone before the tap,
  // and the envelope only opens inside this one HA config flow.
  $effect(() => {
    const target = drive && isExportable(drive) ? drive : null;
    deliveryUrl = null;
    error = null;
    if (!target) return;
    let cancelled = false;
    (async () => {
      try {
        // Plaintext bundle on purpose: the envelope already encrypts it to a
        // key that only this one HA config flow holds, and a passphrase would
        // just be one more thing to type into HA.
        const envelope = await encryptHandoff(request, await exportBundleText([target]));
        if (!cancelled) deliveryUrl = handoffDeliveryUrl(request, envelope);
      } catch (caught) {
        if (cancelled) return;
        error = caught instanceof Error ? caught.message : String(caught);
        addLog(`Handoff to Home Assistant failed: ${error}`, 'error');
      }
    })();
    return () => {
      cancelled = true;
    };
  });

  // A top-level navigation, not a fetch: the CSP's connect-src 'none' stays
  // intact. target="_blank" keeps this app where it is.
  function delivered() {
    sent = true;
    addLog(`Key for ${request.address} handed to Home Assistant at ${request.host}.`);
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
  {:else if sent}
    <div class="notice success">
      A new tab with Home Assistant opened and should confirm that the key was received. Go back to the
      Home Assistant setup dialog and press <strong>Submit</strong>.
    </div>
  {:else}
    <p>
      Send the key of <strong>{displayName(drive)}</strong>? Home Assistant can then open this garage
      door whenever it wants.
    </p>
    <div class="row">
      {#if deliveryUrl}
        <a
          class="button primary"
          href={deliveryUrl}
          target="_blank"
          rel="noopener noreferrer"
          onclick={delivered}
        >
          Send key to Home Assistant
        </a>
      {:else if !error}
        <button class="primary" disabled>Encrypting…</button>
      {/if}
    </div>
  {/if}

  {#if error}
    <div class="notice danger">{error}</div>
  {/if}

  <div class="row" style="margin-top: 0.75rem">
    <button onclick={onclose}>{sent ? 'Done' : 'Cancel'}</button>
  </div>
</div>
