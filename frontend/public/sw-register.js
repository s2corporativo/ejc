// Registro do service worker (externalizado p/ permitir CSP script-src 'self')
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  });
}
