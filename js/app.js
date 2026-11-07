(function () {
  "use strict";

  const $ = function (selector, root) { return (root || document).querySelector(selector); };
  const $$ = function (selector, root) { return Array.from((root || document).querySelectorAll(selector)); };
  const urlInput = $("#videoUrl");
  const videoCard = $("#videoCard");
  let activeFormat = AppSettings.get("defaultFormat");
  let activeQuality = AppSettings.get("defaultQuality");
  let currentVideo = null;
  let analysisRequest = 0;
  let progressTimer = null;
  const platforms = [
    { match: /(^|\.)youtube\.com$|(^|\.)youtu\.be$/, name: "YouTube", icon: "▶" },
    { match: /(^|\.)tiktok\.com$/, name: "TikTok", icon: "♪" },
    { match: /(^|\.)instagram\.com$/, name: "Instagram", icon: "◎" },
    { match: /(^|\.)vimeo\.com$/, name: "Vimeo", icon: "V" },
    { match: /(^|\.)facebook\.com$|(^|\.)fb\.watch$/, name: "Facebook", icon: "f" },
    { match: /(^|\.)x\.com$|(^|\.)twitter\.com$/, name: "X", icon: "𝕏" },
    { match: /(^|\.)soundcloud\.com$/, name: "SoundCloud", icon: "♫" },
    { match: /(^|\.)twitch\.tv$/, name: "Twitch", icon: "▣" },
    { match: /(^|\.)dailymotion\.com$/, name: "Dailymotion", icon: "▶" }
  ];

  function errMsg(error) {
    const status = error && error.status;
    if (status === 403) return t("er.403");
    if (status === 422) return t("er.422");
    if (status === 502) return t("er.502");
    return t("er.x");
  }

  function playSound() {
    if (!AppSettings.get("soundEnabled")) return Promise.resolve();
    const audio = new Audio("assets/sounds/notification.wav");
    audio.volume = Math.max(0, Math.min(1, Number(AppSettings.get("soundVolume")) / 100));
    return audio.play();
  }

  let aboutInfo = null;
  function renderAbout() {
    const element = $("#aboutVersions");
    if (element && aboutInfo) element.textContent = t("ab.ver", { y: aboutInfo.ytDlp || "—", f: aboutInfo.ffmpeg || "—" });
  }

  function toast(message, type, title) {
    const region = $("#toastRegion");
    const item = document.createElement("div");
    item.className = "toast " + (type || "");
    const text = document.createElement("div");
    if (title) {
      const heading = document.createElement("span");
      heading.className = "toast-title";
      heading.textContent = title;
      text.appendChild(heading);
    }
    text.appendChild(document.createTextNode(message));
    item.appendChild(text);
    region.appendChild(item);
    window.setTimeout(function () { item.remove(); }, 4200);
  }

  function showDrawer(name) {
    const drawer = $("#" + name + "Drawer");
    const other = name === "history" ? $("#settingsDrawer") : $("#historyDrawer");
    other.classList.remove("open");
    other.setAttribute("aria-hidden", "true");
    other.inert = true;
    drawer.inert = false;
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    $("#scrim").hidden = false;
    document.body.classList.add("drawer-open");
  }

  function closeDrawers() {
    $$(".drawer").forEach(function (drawer) {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
      drawer.inert = true;
    });
    $("#scrim").hidden = true;
    document.body.classList.remove("drawer-open");
  }

  function setTab(name) {
    $$(".settings-tab").forEach(function (tab) { tab.classList.toggle("active", tab.dataset.tab === name); });
    $$(".settings-page").forEach(function (page) { page.classList.toggle("active", page.dataset.page === name); });
    $(".settings-scroll").scrollTop = 0;
  }

  function getPlatform(hostname) {
    const host = hostname.toLowerCase().replace(/^www\./, "");
    return platforms.find(function (item) { return item.match.test(host); }) || {
      name: host || "Web",
      icon: "↗"
    };
  }

  function setPlatformBadge(element, platform) {
    element.replaceChildren();
    const icon = document.createElement("span");
    icon.className = "platform-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = platform.icon;
    element.append(icon, document.createTextNode(" " + platform.name));
  }

  function buildQualityOptions(qualities) {
    const container = $("#qualityOptions");
    container.replaceChildren();
    const videoQualities = Array.isArray(qualities) ? qualities : [];
    videoQualities.forEach(function (quality) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pill";
      button.dataset.quality = quality;
      button.textContent = quality;
      button.addEventListener("click", function () {
        activeQuality = quality;
        $$(".quality-options .pill").forEach(function (pill) { pill.classList.toggle("active", pill === button); });
      });
      container.appendChild(button);
    });
    const savedQuality = String(activeQuality).match(/^\d+p/);
    const desired = activeQuality === "Kaynağın en iyisi" ? videoQualities[0] : savedQuality ? savedQuality[0] : activeQuality;
    const selected = $$(".quality-options .pill").find(function (button) { return button.dataset.quality === desired; }) ||
      $(".quality-options .pill");
    if (selected) {
      selected.classList.add("active");
      activeQuality = selected.dataset.quality;
    }
  }

  async function analyzeLink(value) {
    let raw = (value || "").trim();
    if (!raw) {
      toast(t("r.nolink"), "error");
      urlInput.focus();
      return;
    }
    if (!/^[a-z][a-z\d+.-]*:\/\//i.test(raw)) raw = "https://" + raw;
    let url;
    try {
      url = new URL(raw);
    } catch (error) {
      toast(t("r.bad"), "error");
      return;
    }
    if (!["http:", "https:"].includes(url.protocol)) {
      toast(t("r.http"), "error");
      return;
    }
    if (AppSettings.get("httpsOnly") && url.protocol !== "https:") {
      toast(t("r.https"), "error");
      return;
    }
    urlInput.value = url.href;
    const requestId = ++analysisRequest;
    const platform = getPlatform(url.hostname);
    setPlatformBadge($("#platformPill"), platform);
    $("#platformPill").hidden = false;
    $("#platformHint").textContent = t("r.load");
    $("#linkProgress").style.width = "35%";
    videoCard.hidden = true;
    $("#emptyNote").hidden = true;
    $("#downloadButton").setAttribute("aria-label", t("btn.analyze"));
    if (!window.DesktopBackend.isConnected()) {
      $("#linkProgress").style.width = "0";
      $("#emptyNote").hidden = false;
      toast(t("r.nobe"), "error");
      return false;
    }
    try {
      const info = await window.DesktopBackend.getVideoInfo(url.href);
      if (requestId !== analysisRequest) return false;
      currentVideo = info;
      platform.name = info.platform || platform.name;
      setPlatformBadge($("#platformPill"), platform);
      $("#videoTitle").textContent = info.title || "Video";
      $("#videoSubtitle").textContent = [info.channel, platform.name].filter(Boolean).join(" · ");
      $("#videoDuration").textContent = info.durationLabel || "—";
      const thumbnail = $("#videoThumbnail");
      const oldImage = $(".thumbnail-image", thumbnail);
      if (oldImage) oldImage.remove();
      if (info.thumbnail && /^https:\/\//i.test(info.thumbnail)) {
        const image = document.createElement("img");
        image.className = "thumbnail-image";
        image.src = info.thumbnail;
        image.alt = "";
        image.referrerPolicy = "no-referrer";
        $(".thumbnail-art", thumbnail).prepend(image);
      }
      buildQualityOptions(info.qualities);
      const formatButtons = $$(".format-row > [data-format]");
      formatButtons.forEach(function (button) {
        const available = button.dataset.format === "MP4" ? info.hasVideo : info.hasAudio;
        button.disabled = !available;
      });
      if ((activeFormat === "MP4" && !info.hasVideo) || (activeFormat === "MP3" && !info.hasAudio)) {
        activeFormat = info.hasVideo ? "MP4" : "MP3";
      }
      const formatButton = $('.format-row [data-format="' + activeFormat + '"]');
      if (formatButton) handleFormat(formatButton);
      $("#thumbnailOption").checked = AppSettings.get("saveThumbnail");
      $("#subtitleOption").checked = AppSettings.get("includeSubtitles");
      $("#platformHint").textContent = info.qualities.length
        ? t("r.qn", { p: platform.name, n: info.qualities.length })
        : t("r.nos", { p: platform.name });
      videoCard.hidden = false;
      $("#emptyNote").hidden = true;
      $("#linkProgress").style.width = "100%";
      $("#downloadButton").setAttribute("aria-label", t("btn.reanalyze"));
      return true;
    } catch (error) {
      if (requestId === analysisRequest) {
        currentVideo = null;
        $("#linkProgress").style.width = "0";
        $("#platformHint").textContent = "";
        $("#emptyNote").hidden = false;
        toast(errMsg(error), "error");
      }
      return false;
    }
  }

  function handleFormat(button) {
    if (button.disabled) return;
    activeFormat = button.dataset.format;
    $$(".format-row > [data-format]").forEach(function (item) { item.classList.toggle("active", item === button); });
    const audioOnly = activeFormat === "MP3";
    $(".separator").hidden = audioOnly;
    $("#qualityOptions").hidden = audioOnly;
    $("#thumbnailOption").disabled = audioOnly;
    $("#subtitleOption").disabled = audioOnly;
  }

  async function startDownload(item) {
    if (item && item.url) {
      urlInput.value = item.url;
      activeFormat = item.format || activeFormat;
      activeQuality = item.quality || activeQuality;
      if (!await analyzeLink(item.url)) return;
      const formatButton = $('.format-row [data-format="' + activeFormat + '"]');
      if (formatButton) handleFormat(formatButton);
    }
    if (videoCard.hidden || !currentVideo) {
      toast(t("r.first"), "error");
      return;
    }
    if (!window.DesktopBackend.isConnected()) {
      toast(t("r.nobe"), "error");
      return;
    }
    $("#downloadState").hidden = false;
    $("#startDownload").hidden = true;
    $(".state-label").textContent = t("r.send");
    $("#progressPercent").textContent = "—";
    $("#downloadProgress").style.width = "0";
    try {
      const task = await window.DesktopBackend.startDownload({
        url: urlInput.value,
        format: activeFormat,
        quality: activeFormat === "MP3" ? "audio" : activeQuality,
        folder: AppSettings.get("downloadFolder"),
        saveThumbnail: $("#thumbnailOption").checked,
        subtitles: $("#subtitleOption").checked
      });
      $("#downloadProgress").style.width = Math.max(0, Math.min(100, task.progress || 0)) + "%";
      $("#progressPercent").textContent = Math.round(task.progress || 0) + "%";
      $(".state-label").textContent = t(task.status === "queued" ? "st.q" : "st.d");
      pollDownload(task.id);
    } catch (error) {
      $("#downloadState").hidden = true;
      $("#startDownload").hidden = false;
      toast(errMsg(error), "error");
    }
  }

  function formatSpeed(bytesPerSecond) {
    if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "";
    return bytesPerSecond >= 1024 * 1024
      ? (bytesPerSecond / (1024 * 1024)).toFixed(1) + " " + t("u.mb")
      : Math.round(bytesPerSecond / 1024) + " " + t("u.kb");
  }

  function formatEta(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "";
    const minutes = Math.floor(seconds / 60);
    const remainder = Math.floor(seconds % 60);
    return minutes ? minutes + " " + t("u.m") + " " + remainder + " " + t("u.s") : remainder + " " + t("u.s");
  }

  function pollDownload(downloadId) {
    window.clearInterval(progressTimer);
    const poll = async function () {
      if (document.hidden) return;
      try {
        const task = await window.DesktopBackend.getDownload(downloadId);
        const progress = Math.max(0, Math.min(100, Number(task.progress) || 0));
        $("#downloadProgress").style.width = progress + "%";
        $("#progressPercent").textContent = Math.round(progress) + "%";
        const statusLabels = {
          queued: t("st.qw"),
          downloading: t("st.d") + (formatSpeed(task.speed) ? " · " + formatSpeed(task.speed) : "") +
            (formatEta(task.eta) ? " · " + formatEta(task.eta) : ""),
          processing: t("st.p"),
          completed: t("st.ok"),
          failed: t("st.f"),
          cancelled: t("st.c")
        };
        $(".state-label").textContent = statusLabels[task.status] || t("st.x");
        if (task.status === "completed") {
          window.clearInterval(progressTimer);
          $("#downloadState").hidden = true;
          $("#startDownload").hidden = false;
          const entry = DownloadHistory.add({
            id: task.id,
            title: task.title || currentVideo.title,
            platform: task.platform || currentVideo.platform,
            format: task.format,
            quality: task.quality,
            duration: task.duration || currentVideo.durationLabel,
            thumbnail: task.thumbnail || currentVideo.thumbnail,
            url: task.url || urlInput.value,
            filepath: task.filepath,
            folder: task.filepath ? task.filepath.replace(/[\\/][^\\/]+$/, "") : task.folder
          });
          if (AppSettings.get("notificationsEnabled")) toast(t("r.saved", { p: task.filepath }), "success", task.title || t("r.done"));
          playSound().catch(function () {});
          if (AppSettings.get("openFolderAfterDownload") && window.pywebview && window.pywebview.api) {
            const folder = entry.folder || AppSettings.get("downloadFolder");
            window.pywebview.api.open_download_folder(folder).catch(function (error) {
              toast(t("r.fo", { m: error.message }), "error");
            });
          }
          return;
        }
        if (task.status === "failed" || task.status === "cancelled") {
          window.clearInterval(progressTimer);
          $("#downloadState").hidden = true;
          $("#startDownload").hidden = false;
          toast(task.error || t("r.fail"), "error");
        }
      } catch (error) {
        window.clearInterval(progressTimer);
        $("#downloadState").hidden = true;
        $("#startDownload").hidden = false;
        toast(t("r.sf", { m: error.message }), "error");
      }
    };
    poll();
    progressTimer = window.setInterval(poll, 1000);
  }

  async function readClipboardText() {
    const result = await window.DesktopBackend.readClipboard();
    return ((result && result.text) || "").trim();
  }

  async function pasteFromClipboard() {
    try {
      const text = await readClipboardText();
      if (!text) {
        toast(t("r.noclip"), "error");
        return;
      }
      urlInput.value = text;
      handleInputChange();
      analyzeLink(text);
    } catch (error) {
      toast(t("r.clipf"), "error");
      urlInput.focus();
    }
  }

  let clipboardLastInspect = 0;
  let clipboardLastText = "";
  async function inspectClipboard() {
    const now = Date.now();
    if (now - clipboardLastInspect < 2000) return;
    clipboardLastInspect = now;
    if (!AppSettings.get("clipboardDetection") || document.activeElement === urlInput) return;
    try {
      const text = await readClipboardText();
      if (!text || text === clipboardLastText || text === urlInput.value.trim() || !/^https?:\/\//i.test(text)) return;
      clipboardLastText = text;
      urlInput.value = text;
      handleInputChange();
      analyzeLink(text);
      toast(t("r.clip"), "success");
    } catch (error) {
      // The clipboard is read by the desktop backend, so no browser permission prompt is involved.
    }
  }

  function handleInputChange() {
    const raw = urlInput.value.trim();
    $(".link-box").classList.toggle("has-link", raw.length > 0);
    if (!raw) {
      $("#platformPill").hidden = true;
      return;
    }
    try {
      const url = new URL(raw);
      const platform = getPlatform(url.hostname);
      setPlatformBadge($("#platformPill"), platform);
      $("#platformPill").hidden = false;
    } catch (error) {
      $("#platformPill").hidden = true;
    }
  }

  async function init() {
    const bootstrap = await window.DesktopBackend.initialize();
    AppSettings.init(bootstrap && bootstrap.settings);
    I18n.setLanguage(AppSettings.get("language"));
    closeDrawers();
    ColorPicker.init();
    DownloadHistory.init(bootstrap && bootstrap.history);
    document.documentElement.style.setProperty("--led-speed", (11 - Number(AppSettings.get("ledSpeed"))) + "s");
    document.documentElement.style.setProperty("--led-brightness", Number(AppSettings.get("ledBrightness")) / 100);
    document.documentElement.style.setProperty("--led-density", Math.max(130, 235 - Number(AppSettings.get("ledDensity"))) + "deg");
    document.body.classList.toggle("reduce-motion", AppSettings.get("reduceMotion"));
    $("#appWindow").classList.toggle("led-off", !AppSettings.get("ledEnabled"));

    $("#settingsOpen").addEventListener("click", function () { showDrawer("settings"); });
    $("#historyOpen").addEventListener("click", function () { showDrawer("history"); });
    $("#scrim").addEventListener("click", closeDrawers);
    $$("[data-close-drawer]").forEach(function (button) { button.addEventListener("click", closeDrawers); });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") closeDrawers(); });
    $$(".settings-tab").forEach(function (tab) { tab.addEventListener("click", function () { setTab(tab.dataset.tab); }); });
    $("#linkForm").addEventListener("submit", function (event) {
      event.preventDefault();
      analyzeLink(urlInput.value);
    });
    urlInput.addEventListener("input", handleInputChange);
    $("#pasteButton").addEventListener("click", pasteFromClipboard);
    $$(".format-row [data-format]").forEach(function (button) {
      button.addEventListener("click", function () { handleFormat(button); });
    });
    const defaultFormatButton = $('.format-row [data-format="' + activeFormat + '"]');
    if (defaultFormatButton) handleFormat(defaultFormatButton);
    $("#startDownload").addEventListener("click", function () { startDownload(); });
    $("#clearHistory").addEventListener("click", function () {
      if (!DownloadHistory.all().length) {
        toast(t("r.nohist"));
        return;
      }
      if (window.confirm(t("r.chist"))) {
        DownloadHistory.clear();
        toast(t("r.hcl"), "success");
      }
    });
    $("#browseFolder").addEventListener("click", async function () {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_folder) {
        try {
          const selectedFolder = await window.pywebview.api.choose_folder();
          if (selectedFolder) {
            $("#downloadFolder").value = selectedFolder;
            AppSettings.set("downloadFolder", selectedFolder);
          }
        } catch (error) {
          toast(t("r.ff", { m: error.message }), "error");
        }
        return;
      }
      const selected = window.prompt(t("r.pf"), AppSettings.get("downloadFolder"));
      if (selected !== null && selected.trim()) {
        $("#downloadFolder").value = selected.trim();
        AppSettings.set("downloadFolder", selected.trim());
      }
    });
    $("#resetSettings").addEventListener("click", function () {
      if (window.confirm(t("r.cr"))) {
        AppSettings.reset();
        toast(t("r.rd"), "success");
      }
    });
    $("#previewSound").addEventListener("click", function () {
      const audio = new Audio("assets/sounds/notification.wav");
      audio.volume = Number(AppSettings.get("soundVolume")) / 100;
      audio.play().then(function () { toast(t("r.sp"), "success"); }).catch(function () { toast(t("r.sf2"), "error"); });
    });
    $("#clearTempFiles").addEventListener("click", async function () {
      try {
        const result = await window.DesktopBackend.cleanupTemporaryFiles(AppSettings.get("downloadFolder"));
        toast(result.removed ? t("r.tr", { n: result.removed }) : t("r.tn"), "success");
      } catch (error) {
        toast(t("r.tf", { m: error.message }), "error");
      }
    });
    $("#checkUpdates").addEventListener("click", async function () {
      toast(t("ab.chk"));
      try {
        const result = await window.DesktopBackend.checkUpdates();
        toast(result.upToDate ? t("ab.ok", { v: result.current }) : t("ab.new", { v: result.latest, c: result.current }), result.upToDate ? "success" : "");
      } catch (error) {
        toast(t("ab.fail"), "error");
      }
    });
    AppSettings.onChange(function (key, value, settings) {
      const current = settings || AppSettings.get();
      if (key === "ledEnabled" || key === "*") $("#appWindow").classList.toggle("led-off", !current.ledEnabled);
      if (key === "ledSpeed" || key === "*") document.documentElement.style.setProperty("--led-speed", (11 - Number(current.ledSpeed)) + "s");
      if (key === "ledBrightness" || key === "*") document.documentElement.style.setProperty("--led-brightness", Number(current.ledBrightness) / 100);
      if (key === "ledDensity" || key === "*") document.documentElement.style.setProperty("--led-density", Math.max(130, 235 - Number(current.ledDensity)) + "deg");
      if (key === "reduceMotion" || key === "*") document.body.classList.toggle("reduce-motion", Boolean(current.reduceMotion));
      if (key === "defaultFormat" && videoCard.hidden) activeFormat = value;
      if (key === "defaultQuality" && videoCard.hidden) activeQuality = value;
      if (key === "saveThumbnail") $("#thumbnailOption").checked = Boolean(value);
      if (key === "includeSubtitles") $("#subtitleOption").checked = Boolean(value);
      if (key === "language") I18n.setLanguage(value);
      if (key !== "*") {
        $("#saveStatus").textContent = t("f.saved");
        window.setTimeout(function () { $("#saveStatus").textContent = t("f.auto"); }, 1300);
      }
    });
    window.addEventListener("app:toast", function (event) { toast(event.detail.message, event.detail.type); });
    window.addEventListener("app:backend-error", function (event) {
      toast(t("r.db"), "error");
    });
    window.addEventListener("app:storage-error", function () { toast(t("r.stf"), "error"); });
    window.addEventListener("history:repeat", function (event) { closeDrawers(); startDownload(event.detail); });
    window.addEventListener("history:location", async function (event) {
      const api = window.pywebview && window.pywebview.api;
      if (!api || !api.open_download_folder) {
        toast(t("r.nd", { p: event.detail.folder || AppSettings.get("downloadFolder") }));
        return;
      }
      try {
        await api.open_download_folder(event.detail.folder || AppSettings.get("downloadFolder"));
      } catch (error) {
        toast(t("r.fo", { m: error.message }), "error");
      }
    });
    window.addEventListener("paste", function (event) {
      if (!AppSettings.get("clipboardDetection")) return;
      const text = event.clipboardData && event.clipboardData.getData("text");
      if (!text || !/^https?:\/\//i.test(text.trim())) return;
      urlInput.value = text.trim();
      handleInputChange();
      analyzeLink(text);
    });
    window.addEventListener("i18n:change", renderAbout);
    window.DesktopBackend.getAbout().then(function (info) { aboutInfo = info; renderAbout(); }).catch(function () {});
    window.addEventListener("focus", inspectClipboard);
    // Pause the LED border animation while the window is in the background.
    const syncActivity = function () {
      document.body.classList.toggle("app-inactive", document.hidden || !document.hasFocus());
    };
    window.addEventListener("blur", syncActivity);
    window.addEventListener("focus", syncActivity);
    document.addEventListener("visibilitychange", syncActivity);
    syncActivity();
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") inspectClipboard();
    });
  }

  document.addEventListener("DOMContentLoaded", init, { once: true });
}());
