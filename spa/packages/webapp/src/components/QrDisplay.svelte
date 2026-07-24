<script lang="ts">
  import qrcode from 'qrcode-generator';

  interface Props {
    /** The text to encode - here always a credential bundle (HMOLES1:/HMOLES1E:). */
    text: string;
    /** Rendered edge length in CSS pixels. */
    size?: number;
  }

  const { text, size = 260 }: Props = $props();

  // Error-correction level L (7%): the code is shown on a clean screen and
  // scanned straight away, so spending modules on damage tolerance only makes
  // it denser and harder for a phone camera to resolve. Mirrors the CLI's
  // `export` QR (see cli.py `_print_qr`).
  const model = $derived.by(() => {
    try {
      const qr = qrcode(0, 'L'); // 0 = pick the smallest version that fits
      qr.addData(text);
      qr.make();
      const count = qr.getModuleCount();
      // A quiet zone of 4 modules is required by the spec for reliable scanning.
      const quiet = 4;
      const cells: { x: number; y: number }[] = [];
      for (let row = 0; row < count; row++) {
        for (let col = 0; col < count; col++) {
          if (qr.isDark(row, col)) cells.push({ x: col + quiet, y: row + quiet });
        }
      }
      return { dimension: count + quiet * 2, cells, error: null as string | null };
    } catch {
      // qrcode-generator throws when the data exceeds even a version-40 symbol.
      // For us that only happens with several encrypted drives in one bundle.
      return {
        dimension: 0,
        cells: [],
        error: 'Too much data for a single QR code - export one drive at a time, or use a link or file.',
      };
    }
  });
</script>

{#if model.error}
  <div class="notice warning">{model.error}</div>
{:else}
  <!-- Rendered as inline SVG built from the module matrix, so nothing is
       injected as HTML and the image stays crisp at any size. White background
       included: a transparent QR is unreadable on a dark theme. -->
  <svg
    width={size}
    height={size}
    viewBox="0 0 {model.dimension} {model.dimension}"
    role="img"
    aria-label="QR code containing the credential bundle"
    style="background:#fff; border-radius:0.5rem; display:block"
    shape-rendering="crispEdges"
  >
    {#each model.cells as cell (cell.x + ',' + cell.y)}
      <rect x={cell.x} y={cell.y} width="1" height="1" fill="#000" />
    {/each}
  </svg>
{/if}
