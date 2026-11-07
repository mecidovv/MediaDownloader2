(function () {
  "use strict";

  const STORAGE_KEY = "mediaDownloader.settings.v1";
  const defaults = {
    downloadFolder: "Videos\\MediaDownloader",
    defaultFormat: "MP4",
    defaultQuality: "Kaynağın en iyisi",
    fileNameTemplate: "{title} - {quality}",
    ledEnabled: true,
    ledSpeed: 4.5,
    ledBrightness: 75,
    ledDensity: 65,
    reduceMotion: false,
    accentColor: "#E0142B",
    recentColors: [],
    clipboardDetection: true,
    openFolderAfterDownload: false,
    saveThumbnail: false,
    includeSubtitles: false,
    notificationsEnabled: true,
    soundEnabled: true,
    soundVolume: 45,
    maxDownloads: 2,
    speedLimit: 0,
    retryCount: 2,
    downloadLogs: true,
    startWithWindows: false,
    minimizeToTray: false,
    httpsOnly: true,
    externalContent: true,
    language: "tr",
    schemaVersion: 1
  };
  let values = readStored();
  const subscribers = new Set();

  function readStored() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return Object.assign({}, defaults, saved);
    } catch (error) {
      window.dispatchEvent(new CustomEvent("app:storage-error", { detail: error }));
      return Object.assign({}, defaults);
    }
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch (error) {
      window.dispatchEvent(new CustomEvent("app:storage-error", { detail: error }));
    }
  }

  function emit(key, value) {
    subscribers.forEach(function (callback) { callback(key, value, values); });
    window.dispatchEvent(new CustomEvent("settings:change", { detail: { key: key, value: value } }));
  }

  function set(key, value) {
    if (!Object.prototype.hasOwnProperty.call(defaults, key)) return;
    values[key] = value;
    save();
    if (window.DesktopBackend) window.DesktopBackend.saveSettings(values);
    emit(key, value);
  }

  function bindControls() {
    document.querySelectorAll("[data-setting]").forEach(function (control) {
      const key = control.dataset.setting;
      const value = values[key];
      if (control.type === "checkbox") control.checked = Boolean(value);
      else if (value !== undefined) control.value = String(value);
      updateOutput(control);
      control.addEventListener("input", function () {
        if (control.type === "range") {
          updateOutput(control);
          set(key, Number(control.value));
        } else if (control.type !== "checkbox") {
          set(key, control.type === "number" ? Number(control.value) : control.value);
        }
      });
      control.addEventListener("change", function () {
        if (control.type === "checkbox") set(key, control.checked);
        else if (control.type !== "range") set(key, control.type === "number" ? Number(control.value) : control.value);
      });
    });
  }

  function updateOutput(control) {
    const output = document.querySelector('[data-output="' + control.id + '"]');
    if (!output) return;
    const suffix = control.id === "ledSpeed" ? " sn" : "%";
    output.textContent = control.value + (control.id === "ledSpeed" ? " " + (window.t ? window.t("u.s") : "sn") : "%");
  }

  function reset() {
    values = Object.assign({}, defaults, { schemaVersion: 2 });
    save();
    if (window.DesktopBackend) window.DesktopBackend.saveSettings(values);
    bindValues();
    emit("*", values);
  }

  function bindValues() {
    document.querySelectorAll("[data-setting]").forEach(function (control) {
      const value = values[control.dataset.setting];
      if (control.type === "checkbox") control.checked = Boolean(value);
      else if (value !== undefined) control.value = String(value);
      updateOutput(control);
    });
  }

  function onChange(callback) {
    subscribers.add(callback);
    return function () { subscribers.delete(callback); };
  }

  window.AppSettings = {
    defaults: defaults,
    get: function (key) { return key ? values[key] : Object.assign({}, values); },
    set: set,
    reset: reset,
    onChange: onChange,
    init: function (backendSettings) {
      if (backendSettings && typeof backendSettings === "object") {
        values = Object.assign({}, defaults, backendSettings);
        save();
      }
      if (Number(values.schemaVersion || 1) < 2) {
        values.externalContent = true;
        values.schemaVersion = 2;
        save();
        if (window.DesktopBackend) window.DesktopBackend.saveSettings(values);
      }
      bindControls();
    }
  };
}());
