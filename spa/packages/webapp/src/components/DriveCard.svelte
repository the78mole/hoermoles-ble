<script lang="ts">
  import {
    GATE_ACTIONS,
    type DecodedLogEntry,
    type GateAction,
    type StoredCredential,
  } from 'hoermoles-ble-js';

  import { credentialsFor, displayName, forgetDrive, renameDrive } from '../lib/drives.svelte';
  import { addLog, pickDrive, readDriveLog, sendChannel } from '../lib/session.svelte';
  import Icon, { type IconName } from './Icon.svelte';
  import LogView from './LogView.svelte';

  interface Props {
    drive: StoredCredential;
    device: BluetoothDevice | null;
    onDeviceChange: (device: BluetoothDevice) => void;
    bluetoothAvailable: boolean;
  }

  const { drive, device, onDeviceChange, bluetoothAvailable }: Props = $props();

  let busy = $state<GateAction | null>(null);
  let status = $state<{ kind: 'success' | 'danger'; text: string } | null>(null);
  let showMore = $state(false);
  let showInfo = $state(false);
  let editing = $state(false);
  let draftName = $state('');
  let confirmForget = $state(false);

  let loadingLog = $state(false);
  let logEntries = $state<DecodedLogEntry[] | null>(null);

  // Icon + label for each action. Only `impulse` is verified against real
  // hardware; the rest are derived from the decompiled app and may behave
  // differently or do nothing - that caveat lives in the info panel now that
  // they are promoted to direct buttons, rather than hiding them all.
  const ACTIONS: Record<GateAction, { icon: IconName; label: string }> = {
    impulse: { icon: 'touch_app', label: 'Impulse' },
    open: { icon: 'garage_door_open', label: 'Open' },
    close: { icon: 'garage_door', label: 'Close' },
    light: { icon: 'lightbulb', label: 'Light' },
    partial: { icon: 'indeterminate_check_box', label: 'Partial' },
    ventilation: { icon: 'mode_fan', label: 'Ventilation' },
  };

  // Shown directly; `partial` and `ventilation` hide behind the "more" toggle.
  const PRIMARY_ACTIONS: GateAction[] = ['open', 'close', 'light'];
  const MORE_ACTIONS: GateAction[] = ['partial', 'ventilation'];

  async function trigger(action: GateAction) {
    if (editing) return;
    busy = action;
    status = null;
    try {
      // Picking must happen inside the click handler's task - Web Bluetooth
      // rejects requestDevice() once the user gesture has been lost.
      const target = device ?? (await pickDrive());
      if (target !== device) onDeviceChange(target);

      await sendChannel(target, credentialsFor(drive), GATE_ACTIONS[action]);
      status = { kind: 'success', text: `Sent ${ACTIONS[action].label}` };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog(message, 'error');
      status = { kind: 'danger', text: message };
    } finally {
      busy = null;
    }
  }

  async function loadLog() {
    if (loadingLog || editing) return;
    // A second tap on an open log hides it, so it doubles as a toggle.
    if (logEntries !== null) {
      logEntries = null;
      return;
    }
    loadingLog = true;
    status = null;
    try {
      const target = device ?? (await pickDrive());
      if (target !== device) onDeviceChange(target);
      logEntries = await readDriveLog(target, credentialsFor(drive));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog(message, 'error');
      status = { kind: 'danger', text: message };
    } finally {
      loadingLog = false;
    }
  }

  function startEditing() {
    draftName = drive.label ?? '';
    confirmForget = false;
    editing = true;
  }

  async function saveName() {
    await renameDrive(drive.deviceAddress, draftName);
    editing = false;
  }

  async function forget() {
    await forgetDrive(drive.deviceAddress);
  }
</script>

<div class="card">
  <div class="drive-head">
    {#if editing}
      <input
        class="name-input"
        bind:value={draftName}
        placeholder={drive.productName ?? drive.deviceAddress}
        aria-label="Drive name"
        onkeydown={(e) => e.key === 'Enter' && saveName()}
      />
      <button class="icon-only" title="Save name" aria-label="Save name" onclick={saveName}>
        <Icon name="check" />
      </button>
      <button
        class="icon-only"
        title="Cancel"
        aria-label="Cancel editing"
        onclick={() => (editing = false)}
      >
        <Icon name="close" />
      </button>
    {:else}
      <h2>{displayName(drive)}</h2>
      <button
        class="icon-only"
        aria-pressed={showInfo}
        title="Details"
        aria-label="Show details"
        onclick={() => (showInfo = !showInfo)}
      >
        <Icon name="info" />
      </button>
      <button class="icon-only" title="Rename" aria-label="Rename drive" onclick={startEditing}>
        <Icon name="edit" />
      </button>
    {/if}
  </div>

  {#if showInfo && !editing}
    <div class="notice">
      <div class="info-grid">
        <span>Address</span><code>{drive.deviceAddress}</code>
        <span>Root ID</span><code>{drive.rootId}</code>
        {#if drive.productName}<span>Product</span><span>{drive.productName}</span>{/if}
        {#if drive.serialNo}<span>Serial</span><code>{drive.serialNo}</code>{/if}
      </div>
      <p class="muted" style="margin: 0.5rem 0 0">
        Only <strong>Impulse</strong> is verified against real hardware. Open, Close, Light, Partial and Ventilation
        are derived from the vendor app and may behave differently, or do nothing, depending on how the drive
        is configured.
      </p>
    </div>
  {/if}

  {#if !bluetoothAvailable}
    <p class="muted">Bluetooth is unavailable in this browser - controls are disabled.</p>
  {:else}
    <button
      class="action primary impulse"
      disabled={busy !== null || editing}
      onclick={() => trigger('impulse')}
    >
      <Icon name={ACTIONS.impulse.icon} size={28} />
      <span>{busy === 'impulse' ? 'Sending…' : ACTIONS.impulse.label}</span>
    </button>

    <div class="action-grid">
      {#each PRIMARY_ACTIONS as action (action)}
        <button class="action" disabled={busy !== null || editing} onclick={() => trigger(action)}>
          <Icon name={ACTIONS[action].icon} size={26} />
          <span>{busy === action ? '…' : ACTIONS[action].label}</span>
        </button>
      {/each}
      <button
        class="action"
        aria-pressed={showMore}
        disabled={editing}
        onclick={() => (showMore = !showMore)}
      >
        <Icon name="more_horiz" size={26} />
        <span>{showMore ? 'Less' : 'More'}</span>
      </button>

      {#if showMore}
        {#each MORE_ACTIONS as action (action)}
          <button class="action" disabled={busy !== null || editing} onclick={() => trigger(action)}>
            <Icon name={ACTIONS[action].icon} size={26} />
            <span>{busy === action ? '…' : ACTIONS[action].label}</span>
          </button>
        {/each}
        <button
          class="action"
          aria-pressed={logEntries !== null}
          disabled={loadingLog || editing}
          onclick={loadLog}
        >
          <Icon name="history" size={26} />
          <span>{loadingLog ? '…' : logEntries !== null ? 'Hide log' : 'Log'}</span>
        </button>
      {/if}
    </div>

    {#if logEntries !== null}
      <div class="notice">
        <LogView entries={logEntries} />
      </div>
    {/if}

    {#if !device}
      <p class="muted">You will be asked to pick the drive from the Bluetooth chooser.</p>
    {/if}
  {/if}

  {#if status}
    <div class="notice {status.kind}">{status.text}</div>
  {/if}

  {#if editing}
    <div class="forget-row">
      {#if confirmForget}
        <span class="muted">Delete this credential from this device?</span>
        <div class="row">
          <button class="danger" onclick={forget}>
            <Icon name="delete" size={20} /> Yes, forget it
          </button>
          <button onclick={() => (confirmForget = false)}>Cancel</button>
        </div>
      {:else}
        <button class="danger" onclick={() => (confirmForget = true)}>
          <Icon name="delete" size={20} /> Forget this drive
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .drive-head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  .drive-head h2 {
    flex: 1;
    margin: 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name-input {
    flex: 1;
    font-size: 1.15rem;
    font-weight: 700;
  }
  .icon-only {
    display: grid;
    place-items: center;
    padding: 0.4rem;
    min-height: 0;
    color: var(--text-muted);
    background: none;
    border: none;
  }
  .icon-only:hover:not(:disabled) {
    color: var(--accent);
    border: none;
  }
  .icon-only[aria-pressed='true'] {
    color: var(--accent);
  }

  .info-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.15rem 0.75rem;
    font-size: 0.9rem;
  }
  .info-grid > span:nth-child(odd) {
    color: var(--text-muted);
  }

  /* Icon+label action buttons: big enough for a thumb in a driveway. */
  .action {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.2rem;
    min-height: 4rem;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .action.impulse {
    flex-direction: row;
    gap: 0.5rem;
    width: 100%;
    min-height: 3.75rem;
    font-size: 1.05rem;
    margin-bottom: 0.5rem;
  }
  .action-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
  }
  .forget-row {
    margin-top: 1rem;
  }
  .forget-row .danger {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }
</style>
