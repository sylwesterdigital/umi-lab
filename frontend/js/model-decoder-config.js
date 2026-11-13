/* Set the decoder path before the first <model-viewer> element is created.
 * The official model-viewer global configuration is read during registration.
 * Draco WASM / JS assets are installed under this same-origin path by the
 * UMI release installer, never fetched from Google by the browser.
 */
(() => {
  'use strict';
  const settings = window.ModelViewerElement || {};
  settings.dracoDecoderLocation = '/static/decoders/draco/';
  window.ModelViewerElement = settings;
})();
