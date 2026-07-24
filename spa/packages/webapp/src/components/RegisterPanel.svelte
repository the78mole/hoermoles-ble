<script lang="ts">
  import {
    parseQrCode,
    productClassAndIdFromQrPrefix,
    saveCredential,
    serialNoFromQrPrefix,
  } from 'hoermoles-ble-js';

  import { refreshDrives } from '../lib/drives.svelte';
  import { addLog, pickDrive, withConnection } from '../lib/session.svelte';
  import QrCapture from './QrCapture.svelte';

  interface Props {
    bluetoothAvailable: boolean;
    oncomplete?: () => void;
  }

  const { bluetoothAvailable, oncomplete }: Props = $props();

  let qrText = $state('');
  let allowReexport = $state(true);
  let busy = $state(false);
  let result = $state<{ kind: 'success' | 'danger'; message: string } | null>(null);

  /** Validates the pasted/scanned code before we ask the user to go stand next
   * to the drive - a typo caught here saves a walk. */
  const preview = $derived.by(() => {
    const text = qrText.trim();
    if (text === '') return null;
    try {
      const { prefix, der } = parseQrCode(text);
      if (der.length === 0) return { error: 'No key data found in this code.' };
      const product = productClassAndIdFromQrPrefix(prefix);
      const serial = serialNoFromQrPrefix(prefix);
      return {
        prefix,
        derBytes: der.length,
        productClass: product?.productClass ?? null,
        productId: product?.productId ?? null,
        serial: serial?.toString() ?? null,
      };
    } catch {
      return { error: 'This does not look like a BlueSecur registration code.' };
    }
  });

  async function register() {
    busy = true;
    result = null;
    try {
      const device = await pickDrive();
      const registration = await withConnection(device, (client) =>
        client.register(qrText.trim(), device.id),
      );

      await saveCredential(
        {
          deviceAddress: registration.deviceAddress,
          rootId: registration.rootId,
          rootKey: registration.rootKey,
          qrPrefix: registration.qrPrefix,
          productClass: registration.productClass ?? undefined,
          productId: registration.productId ?? undefined,
          serialNo: registration.serialNo?.toString() ?? null,
          label: device.name ?? undefined,
        },
        { allowReexport },
      );
      registration.rootKey.fill(0);

      await refreshDrives();
      result = {
        kind: 'success',
        message: `Registered successfully (RootID ${registration.rootId}). Export a backup now - see the Export tab.`,
      };
      qrText = '';
      oncomplete?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog(message, 'error');
      result = { kind: 'danger', message };
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2>Register a new drive</h2>

  <div class="notice warning">
    The drive only accepts a new registration while it is in teach-in mode. If it already has an
    administrator you must reset that first, on the drive itself, via <strong
      >menu 19, parameter 02</strong
    >. Otherwise this will time out.
  </div>

  <p class="muted">
    The registration code is the QR code that came with the drive (on the operator, in its manual, or on
    the supplied card).
  </p>

  <QrCapture label="Scan the drive's QR code" onresult={(scanned) => (qrText = scanned)} />

  <label for="register-text">Or paste the code</label>
  <textarea id="register-text" bind:value={qrText} placeholder="03020200…MIIBIjANBgkqhkiG9w0B…"
  ></textarea>

  {#if preview}
    {#if 'error' in preview}
      <div class="notice danger">{preview.error}</div>
    {:else}
      <div class="notice success">
        Looks like a valid code: {preview.derBytes}-byte public key
        {#if preview.serial}&middot; serial {preview.serial}{/if}
        {#if preview.productClass !== null}
          &middot; product class {preview.productClass}/{preview.productId}
        {/if}
      </div>
    {/if}
  {/if}

  <label class="inline">
    <input type="checkbox" bind:checked={allowReexport} />
    Allow exporting this credential later
  </label>
  <p class="muted">
    Recommended <em>on</em> here: registration can only be repeated after resetting the drive, so without an
    export this credential exists in exactly one browser's storage - which the browser is free to evict.
  </p>

  <button
    class="primary"
    disabled={busy || !bluetoothAvailable || preview === null || 'error' in (preview ?? {})}
    onclick={register}
  >
    {busy ? 'Registering…' : 'Register drive'}
  </button>

  {#if !bluetoothAvailable}
    <p class="muted">Registration needs Bluetooth, which this browser does not provide.</p>
  {/if}

  {#if result}
    <div class="notice {result.kind}">{result.message}</div>
  {/if}
</div>
