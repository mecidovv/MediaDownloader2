(function () {
  "use strict";

  const isHttp = window.location.protocol === "http:" || window.location.protocol === "https:";
  const baseUrl = isHttp ? window.location.origin + "/api/v1" : "";
  let connected = false;
  let settingsTimer = null;

  async function request(path, options) {
    const response = await fetch(baseUrl + path, Object.assign({
      headers: { "Content-Type": "application/json" },
      cache: "no-store"
    }, options || {}));
    if (!response.ok) {
      let detail = "Backend isteği başarısız oldu (" + response.status + ").";
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch (error) {
        // Keep the HTTP status as the surfaced error.
      }
      const requestError = new Error(detail);
      requestError.status = response.status;
      throw requestError;
    }
    if (response.status === 204) return null;
    return response.json();
  }

  window.DesktopBackend = {
    isConnected: function () { return connected; },
    initialize: async function () {
      if (!baseUrl) return null;
      try {
        const state = await request("/bootstrap");
        connected = true;
        return state;
      } catch (error) {
        connected = false;
        return null;
      }
    },
    readClipboard: async function () {
      if (!connected) throw new Error("backend not connected");
      return request("/clipboard");
    },
    getAbout: async function () {
      if (!connected) return null;
      return request("/about");
    },
    checkUpdates: async function () {
      if (!connected) throw new Error("backend not connected");
      return request("/about/updates");
    },
    saveSettings: function (settings) {
      if (!connected) return;
      window.clearTimeout(settingsTimer);
      settingsTimer = window.setTimeout(function () {
        request("/settings", { method: "PUT", body: JSON.stringify({ settings: settings }) })
          .catch(function (error) { window.dispatchEvent(new CustomEvent("app:backend-error", { detail: error })); });
      }, 120);
    },
    addHistory: async function (record) {
      if (!connected) return null;
      return request("/history", { method: "POST", body: JSON.stringify(record) });
    },
    clearHistory: async function () {
      if (!connected) return;
      await request("/history", { method: "DELETE" });
    },
    getVideoInfo: async function (url) {
      if (!connected) throw new Error("Masaüstü backend bağlantısı yok.");
      return request("/videos/info", { method: "POST", body: JSON.stringify({ url: url }) });
    },
    startDownload: async function (requestBody) {
      if (!connected) throw new Error("Masaüstü backend bağlantısı yok. İndirme başlatılmadı.");
      return request("/downloads", { method: "POST", body: JSON.stringify(requestBody) });
    },
    getDownload: async function (downloadId) {
      if (!connected) throw new Error("Masaüstü backend bağlantısı yok.");
      return request("/downloads/" + encodeURIComponent(downloadId));
    },
    cancelDownload: async function (downloadId) {
      if (!connected) throw new Error("Masaüstü backend bağlantısı yok.");
      return request("/downloads/" + encodeURIComponent(downloadId), { method: "DELETE" });
    },
    cleanupTemporaryFiles: async function (folder) {
      if (!connected) throw new Error("Masaüstü backend bağlantısı yok.");
      return request("/downloads/cleanup", {
        method: "POST",
        body: JSON.stringify({ folder: folder })
      });
    }
  };
}());
