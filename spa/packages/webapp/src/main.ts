import { mount } from 'svelte';

import App from './App.svelte';
import './app.css';

// The splash markup lives in index.html so it is visible before this bundle has
// even parsed; removing it here is the earliest honest "the app is ready".
document.getElementById('boot-splash')?.remove();

export default mount(App, { target: document.getElementById('app')! });
