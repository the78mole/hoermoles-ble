/**
 * QR scanning for credential import and for the registration code on the drive.
 *
 * Uses the browser's own `BarcodeDetector`, which Chrome on Android ships
 * natively - no WASM decoder, no extra megabyte in the bundle, and it decodes
 * far more reliably than a JS port. Where it is missing (most desktop browsers
 * today) the UI falls back to pasting the code as text, which is why
 * {@link isQrScanningAvailable} exists rather than a hard dependency.
 *
 * The camera stream is strictly local: nothing is uploaded, and the page's CSP
 * (`connect-src 'none'`) makes that structurally true rather than a promise.
 */

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

interface BarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorLike;
  getSupportedFormats?(): Promise<string[]>;
}

function detectorConstructor(): BarcodeDetectorConstructor | null {
  const ctor = (globalThis as { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;
  return ctor ?? null;
}

export function isQrScanningAvailable(): boolean {
  return detectorConstructor() !== null && navigator.mediaDevices?.getUserMedia !== undefined;
}

export class QrScanner {
  private stream: MediaStream | null = null;
  private detector: BarcodeDetectorLike | null = null;
  private frameHandle: number | null = null;
  private stopped = false;

  /**
   * Starts the rear camera and calls `onResult` with the first code found.
   * Returns once the camera is running; scanning continues until {@link stop}
   * or a successful decode.
   */
  async start(video: HTMLVideoElement, onResult: (text: string) => void): Promise<void> {
    const Detector = detectorConstructor();
    if (!Detector)
      throw new Error('This browser cannot scan QR codes - paste the code as text instead.');

    this.detector = new Detector({ formats: ['qr_code'] });
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment' },
      audio: false,
    });

    video.srcObject = this.stream;
    video.setAttribute('playsinline', 'true');
    await video.play();

    const scanFrame = async () => {
      if (this.stopped || !this.detector) return;
      try {
        const codes = await this.detector.detect(video);
        if (codes.length > 0 && codes[0].rawValue) {
          onResult(codes[0].rawValue);
          this.stop();
          return;
        }
      } catch {
        // Individual frames fail routinely (camera warming up, motion blur) -
        // keep going rather than tearing the scanner down.
      }
      this.frameHandle = requestAnimationFrame(() => void scanFrame());
    };
    this.frameHandle = requestAnimationFrame(() => void scanFrame());
  }

  stop(): void {
    this.stopped = true;
    if (this.frameHandle !== null) cancelAnimationFrame(this.frameHandle);
    this.frameHandle = null;
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
    this.detector = null;
  }
}
