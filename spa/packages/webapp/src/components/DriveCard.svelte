<script lang="ts">
  import { GATE_ACTIONS, type GateAction, type StoredCredential } from 'hoermoles-ble-js';

  import { credentialsFor, displayName, forgetDrive } from '../lib/drives.svelte';
  import { addLog, pickDrive, sendChannel } from '../lib/session.svelte';

  interface Props {
    drive: StoredCredential;
    device: BluetoothDevice | null;
    onDeviceChange: (device: BluetoothDevice) => void;
    bluetoothAvailable: boolean;
  }

  const { drive, device, onDeviceChange, bluetoothAvailable }: Props = $props();

  let busy = $state<GateAction | null>(null);
  let status = $state<{ kind: 'success' | 'danger'; text: string } | null>(null);
  let showAll = $state(false);
  let confirmForget = $state(false);

  // Only `impulse` is verified against real hardware; the rest come from the
  // decompiled defaults table and depend on how the drive was configured. The
  // UI keeps them behind a disclosure rather than presenting all six as equal.
  const VERIFIED: GateAction = 'impulse';
  const DERIVED_ACTIONS: GateAction[] = ['open', 'close', 'light', 'partial', 'ventilation'];

  const ACTION_LABELS: Record<GateAction, string> = {
    impulse: 'Impulse (open / stop / close)',
    open: 'Open',
    close: 'Close',
    light: 'Light',
    partial: 'Partial opening',
    ventilation: 'Ventilation position',
  };

  async function trigger(action: GateAction) {
    busy = action;
    status = null;
    try {
      // Picking must happen inside the click handler's task - Web Bluetooth
      // rejects requestDevice() once the user gesture has been lost.
      const target = device ?? (await pickDrive());
      if (target !== device) onDeviceChange(target);

      await sendChannel(target, credentialsFor(drive), GATE_ACTIONS[action]);
      status = { kind: 'success', text: `Sent ${ACTION_LABELS[action]}` };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog(message, 'error');
      status = { kind: 'danger', text: message };
    } finally {
      busy = null;
    }
  }

  async function forget() {
    await forgetDrive(drive.deviceAddress);
  }
</script>

<div class="card">
  <h2>{displayName(drive)}</h2>
  <p class="muted">
    {drive.deviceAddress} &middot; RootID {drive.rootId}
    {#if drive.productName}&middot; {drive.productName}{/if}
    {#if drive.serialNo}&middot; serial {drive.serialNo}{/if}
  </p>

  {#if !bluetoothAvailable}
    <p class="muted">Bluetooth is unavailable in this browser - controls are disabled.</p>
  {:else}
    <button class="primary big" disabled={busy !== null} onclick={() => trigger(VERIFIED)}>
      {busy === VERIFIED ? 'Sending…' : ACTION_LABELS[VERIFIED]}
    </button>

    {#if !device}
      <p class="muted">You will be asked to pick the drive from the Bluetooth chooser.</p>
    {/if}

    <p>
      <button onclick={() => (showAll = !showAll)}>
        {showAll ? 'Hide' : 'Show'} other channels
      </button>
    </p>

    {#if showAll}
      <div class="notice warning">
        These channels are derived from the decompiled app, not verified against real hardware, and
        depend on how your drive is configured. One of them may do nothing - or something other than its
        name suggests.
      </div>
      <div class="grid">
        {#each DERIVED_ACTIONS as action (action)}
          <button disabled={busy !== null} onclick={() => trigger(action)}>
            {busy === action ? 'Sending…' : ACTION_LABELS[action]}
          </button>
        {/each}
      </div>
    {/if}
  {/if}

  {#if status}
    <div class="notice {status.kind}">{status.text}</div>
  {/if}

  <p style="margin-top: 1rem">
    {#if confirmForget}
      <span class="muted">Delete this credential from this device?</span>
      <span class="row">
        <button class="danger" onclick={forget}>Yes, forget it</button>
        <button onclick={() => (confirmForget = false)}>Cancel</button>
      </span>
    {:else}
      <button class="danger" onclick={() => (confirmForget = true)}>Forget this drive</button>
    {/if}
  </p>
</div>
