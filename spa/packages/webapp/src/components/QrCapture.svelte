<script lang="ts">
  import { onDestroy } from 'svelte';

  import { QrScanner, isQrScanningAvailable } from '../lib/qr';

  interface Props {
    onresult: (text: string) => void;
    label?: string;
  }

  const { onresult, label = 'Scan QR code' }: Props = $props();

  let video: HTMLVideoElement | undefined = $state();
  let scanner: QrScanner | null = null;
  let scanning = $state(false);
  let error = $state<string | null>(null);

  const supported = isQrScanningAvailable();

  async function start() {
    error = null;
    scanning = true;
    // The <video> only exists once `scanning` is true, so wait a tick for
    // Svelte to render it before handing it to the scanner.
    await Promise.resolve();
    if (!video) {
      scanning = false;
      return;
    }
    scanner = new QrScanner();
    try {
      await scanner.start(video, (text) => {
        scanning = false;
        onresult(text);
      });
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
      stop();
    }
  }

  function stop() {
    scanner?.stop();
    scanner = null;
    scanning = false;
  }

  onDestroy(stop);
</script>

{#if !supported}
  <p class="muted">
    This browser has no camera QR scanner (it needs <code>BarcodeDetector</code>, which Chrome on Android
    provides). Paste the code as text instead.
  </p>
{:else if scanning}
  <!-- Live camera preview with no audio and no content to caption. -->
  <video bind:this={video}></video>
  <div class="row">
    <button onclick={stop}>Cancel</button>
  </div>
{:else}
  <button onclick={start}>{label}</button>
{/if}

{#if error}
  <div class="notice danger">{error}</div>
{/if}
