import { mount } from 'svelte';

import App from './App.svelte';
import './app.css';

// The faint page background lives in public/, so its URL depends on the deploy
// base (/hoermoles-ble/app/ on Pages, / locally). Setting it from BASE_URL here
// keeps CSS free of a hardcoded path and works wherever the app is hosted. The
// low-opacity blend over the theme happens in app.css (body::before).
document.documentElement.style.setProperty(
  '--page-bg-image',
  `url("${import.meta.env.BASE_URL}background.webp")`,
);

// The splash markup lives in index.html so it is visible before this bundle has
// even parsed; removing it here is the earliest honest "the app is ready".
document.getElementById('boot-splash')?.remove();

export default mount(App, { target: document.getElementById('app')! });
