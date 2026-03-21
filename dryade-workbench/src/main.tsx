// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { createRoot } from "react-dom/client";
import { registerSW } from 'virtual:pwa-register';
import App from "./App.tsx";
import "./i18n";
import "./index.css";

const updateSW = registerSW({
  onNeedRefresh() {
    window.dispatchEvent(new CustomEvent('pwa-update-available', { detail: { updateSW } }));
  },
  onOfflineReady() {
    console.log('[PWA] App ready for offline use');
  },
});

createRoot(document.getElementById("root")!).render(
  <App />,
);
