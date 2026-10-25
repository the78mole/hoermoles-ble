<script lang="ts">
  import {
    deviceCapabilities,
    parseHandoffLink,
    requestPersistentStorage,
    type HandoffRequest,
  } from 'hoermoles-ble-js';
  import { onMount } from 'svelte';

  import BrowserSupport from './components/BrowserSupport.svelte';
  import DriveCard from './components/DriveCard.svelte';
  import ExportPanel from './components/ExportPanel.svelte';
  import HandoffPanel from './components/HandoffPanel.svelte';
  import ImportPanel from './components/ImportPanel.svelte';
  import LogPanel from './components/LogPanel.svelte';
  import RegisterPanel from './components/RegisterPanel.svelte';
  import { drives, refreshDrives } from './lib/drives.svelte';
  import { addLog } from './lib/session.svelte';

  type Tab = 'drives' | 'add' | 'export' | 'log';

  let tab = $state<Tab>('drives');
  let device = $state<BluetoothDevice | null>(null);
  let persistent = $state<boolean | null>(null);
  let importPrefill = $state('');
  let storageError = $state<string | null>(null);
  let handoff = $state<HandoffRequest | null>(null);
  let handoffError = $state<string | null>(null);

  const capabilities = deviceCapabilities();
  const bluetoothAvailable = capabilities.available && capabilities.secureContext;

  const TABS: { id: Tab; label: string }[] = [
    { id: 'drives', label: 'Drives' },
    { id: 'add', label: 'Add' },
    { id: 'export', label: 'Export' },
    { id: 'log', label: 'Log' },
  ];

  /** Opens the Home Assistant handoff panel if `text` is a handoff link (from
   * the URL at startup or from a scanner). Returns false for anything else, so
   * the caller can treat it as a bundle instead. */
  function openHandoff(text: string): boolean {
    try {
      const request = parseHandoffLink(text);
      if (request === null) return false;
      handoff = request;
      handoffError = null;
    } catch (error) {
      handoff = null;
      handoffError = error instanceof Error ? error.message : String(error);
    }
    window.scrollTo({ top: 0 });
    return true;
  }

  onMount(async () => {
    // IndexedDB can be unavailable outright (private browsing on some
    // browsers, storage disabled by policy) or simply fail to open. Without
    // this the failure surfaces as a "Loading credentials…" that never
    // finishes, with nothing in the UI to explain why.
    try {
      await refreshDrives();
    } catch (error) {
      storageError = error instanceof Error ? error.message : String(error);
      addLog(`Could not read stored credentials: ${storageError}`, 'error');
    }

    // A credential lives in IndexedDB, which the browser may evict under
    // storage pressure. Asking for persistence is best effort - Chrome grants
    // it silently for installed PWAs and usually refuses for a plain tab.
    persistent = await requestPersistentStorage();

    // An import link opens the app with the bundle in the URL fragment, which
    // never reaches the server. Hand it to the import form and strip it from
    // the address bar straight away, so a plaintext bundle does not sit there
    // to be screenshotted or bookmarked.
    const marker = window.location.hash.indexOf('#import=');
    if (marker !== -1) {
      importPrefill = decodeURIComponent(window.location.hash.slice(marker + '#import='.length));
      history.replaceState(null, '', window.location.pathname + window.location.search);
      tab = 'add';
      addLog('Import link detected - the code has been filled in below.');
    }

    // Home Assistant's setup dialog shows a QR code that opens this app with a
    // `#ha=` fragment (see HandoffPanel). It holds no secret - only where to
    // send a key and what to encrypt it to - but strip it all the same, so a
    // reload does not offer the handoff again after the dialog is gone.
    if (window.location.hash.startsWith('#ha=')) {
      openHandoff(window.location.hash);
      history.replaceState(null, '', window.location.pathname + window.location.search);
      tab = 'drives';
    }
  });
</script>

<header>
  <h1>Hoermoles</h1>
  <p class="muted">Hörmann BlueSecur drives over Bluetooth - no vendor app, no cloud.</p>
</header>

<nav class="tabs">
  {#each TABS as entry (entry.id)}
    <button aria-current={tab === entry.id ? 'page' : undefined} onclick={() => (tab = entry.id)}>
      {entry.label}
    </button>
  {/each}
</nav>

<BrowserSupport />

{#if handoffError}
  <div class="notice danger">
    <strong>Cannot send a key to Home Assistant.</strong>
    <p>{handoffError}</p>
    <button onclick={() => (handoffError = null)}>Dismiss</button>
  </div>
{/if}
{#if handoff}
  <HandoffPanel request={handoff} onclose={() => (handoff = null)} />
{/if}

{#if tab === 'drives'}
  {#if storageError}
    <div class="notice danger">
      <strong>Could not read stored credentials.</strong>
      <p>{storageError}</p>
      <p>
        This app keeps credentials in the browser's IndexedDB. If you are in a private window, or site
        data is blocked for this origin, storage is unavailable and nothing can be saved or loaded.
      </p>
    </div>
  {:else if !drives.loaded}
    <p class="muted">Loading credentials…</p>
  {:else if drives.items.length === 0}
    <div class="card">
      <h2>No drives yet</h2>
      <p>
        Either import credentials from the <code>hoermoles-ble</code> CLI, or register a drive directly from
        here.
      </p>
      <button class="primary" onclick={() => (tab = 'add')}>Add a drive</button>
    </div>
  {:else}
    {#each drives.items as drive (drive.deviceAddress)}
      <DriveCard {drive} {device} {bluetoothAvailable} onDeviceChange={(picked) => (device = picked)} />
    {/each}

    {#if persistent === false}
      <div class="notice warning">
        The browser did not grant persistent storage, so it may evict these credentials to reclaim space.
        Keep an export as a backup - installing this app to the home screen usually makes storage
        persistent.
      </div>
    {/if}
  {/if}
{:else if tab === 'add'}
  <ImportPanel prefill={importPrefill} onscan={openHandoff} oncomplete={() => (tab = 'drives')} />
  <RegisterPanel {bluetoothAvailable} oncomplete={() => (tab = 'drives')} />
{:else if tab === 'export'}
  <ExportPanel drives={drives.items} onscan={openHandoff} />
{:else if tab === 'log'}
  <LogPanel />
{/if}
