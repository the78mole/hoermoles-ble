<script lang="ts">
  import { deviceCapabilities } from 'hoermoles-ble-js';

  const capabilities = deviceCapabilities();
</script>

{#if !capabilities.available}
  <div class="notice danger">
    <strong>This browser cannot talk to Bluetooth devices.</strong>
    <p>
      Web Bluetooth is implemented by Chrome and Edge on Android, Windows, macOS and ChromeOS. On Linux
      it additionally needs
      <code>chrome://flags/#enable-experimental-web-platform-features</code>. Safari and Firefox do not
      implement it at all, so iPhones and iPads cannot use the control features here.
    </p>
    <p>Importing, exporting and viewing credentials still work - only connecting to a drive does not.</p>
  </div>
{:else if !capabilities.secureContext}
  <div class="notice danger">
    <strong>Not a secure context.</strong> Web Bluetooth requires HTTPS (or localhost). Open the app over
    <code>https://</code>.
  </div>
{:else if !capabilities.canRememberDevices}
  <div class="notice">
    Your browser cannot remember a paired drive between app starts, so you will be asked to pick it from
    the Bluetooth chooser once per session. Enabling
    <code>chrome://flags/#enable-experimental-web-platform-features</code> turns that into a single tap - it
    is off by default in every current Chrome.
  </div>
{/if}
