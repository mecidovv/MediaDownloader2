(function () {
  "use strict";

  const STORAGE_KEY = "mediaDownloader.history.v1";
  let entries = load();
  const list = document.getElementById("historyList");
  const empty = document.getElementById("historyEmpty");
  const count = document.getElementById("historyCount");

  function load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter(function (item) {
        return item && typeof item.id === "string" && typeof item.title === "string";
      }) : [];
    } catch (error) {
      window.dispatchEvent(new CustomEvent("app:storage-error", { detail: error }));
      return [];
    }
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch (error) {
      window.dispatchEvent(new CustomEvent("app:storage-error", { detail: error }));
    }
  }

  function dayKey(date) {
    return date.getFullYear() + "-" + date.getMonth() + "-" + date.getDate();
  }

  function dayLabel(date) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    if (dateOnly.getTime() === today.getTime()) return t("h.today");
    if (dateOnly.getTime() === yesterday.getTime()) return t("h.yest");
    return date.toLocaleDateString(I18n.locale(), { day: "numeric", month: "long", year: "numeric" }).toLocaleUpperCase(I18n.locale());
  }

  function makeAction(label, icon, callback) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-action";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = icon;
    button.addEventListener("click", callback);
    return button;
  }

  function render() {
    list.replaceChildren();
    const groups = new Map();
    entries.slice().sort(function (a, b) { return new Date(b.downloadedAt) - new Date(a.downloadedAt); }).forEach(function (item) {
      const date = new Date(item.downloadedAt);
      if (Number.isNaN(date.getTime())) return;
      const key = dayKey(date);
      if (!groups.has(key)) groups.set(key, { label: dayLabel(date), items: [] });
      groups.get(key).items.push(item);
    });

    groups.forEach(function (group) {
      const heading = document.createElement("h3");
      heading.className = "history-day";
      heading.textContent = group.label;
      list.appendChild(heading);
      group.items.forEach(function (item) {
        const row = document.createElement("article");
        row.className = "history-item";
        const thumb = document.createElement("div");
        thumb.className = "history-thumb";
        thumb.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z"/></svg>';
        if (item.thumbnail && /^https:\/\//i.test(item.thumbnail)) {
          const image = document.createElement("img");
          image.src = item.thumbnail;
          image.alt = "";
          image.loading = "lazy";
          image.referrerPolicy = "no-referrer";
          thumb.appendChild(image);
        }
        const copy = document.createElement("div");
        copy.className = "history-copy";
        const title = document.createElement("div");
        title.className = "history-name";
        title.textContent = item.title;
        const meta = document.createElement("div");
        meta.className = "history-meta";
        meta.textContent = [item.platform, item.format, item.quality, item.duration].filter(Boolean).join(" · ");
        const date = document.createElement("div");
        date.className = "history-date";
        date.textContent = new Date(item.downloadedAt).toLocaleTimeString(I18n.locale(), { hour: "2-digit", minute: "2-digit" }) + " · " + t("h.done");
        copy.append(title, meta, date);
        const actions = document.createElement("div");
        actions.className = "history-item-actions";
        actions.append(
          makeAction(t("h.again"), '<svg viewBox="0 0 24 24"><path d="M12 4v11m-5-4 5 5 5-5"/></svg>', function () {
            window.dispatchEvent(new CustomEvent("history:repeat", { detail: item }));
          }),
          makeAction(t("h.loc"), '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v6m-3-3 3 3 3-3"/></svg>', function () {
            window.dispatchEvent(new CustomEvent("history:location", { detail: item }));
          })
        );
        row.append(thumb, copy, actions);
        list.appendChild(row);
      });
    });
    count.textContent = t("h.n", { n: entries.length });
    empty.hidden = entries.length > 0;
    list.hidden = entries.length === 0;
  }

  window.DownloadHistory = {
    init: function (initialEntries) {
      if (Array.isArray(initialEntries)) entries = initialEntries;
      render();
    },
    add: function (item) {
      const entry = Object.assign({ id: String(Date.now()), downloadedAt: new Date().toISOString() }, item);
      entries.unshift(entry);
      persist();
      if (window.DesktopBackend) {
        window.DesktopBackend.addHistory(entry).catch(function (error) {
          window.dispatchEvent(new CustomEvent("app:backend-error", { detail: error }));
        });
      }
      render();
      return entry;
    },
    clear: function () {
      entries = [];
      persist();
      if (window.DesktopBackend) {
        window.DesktopBackend.clearHistory().catch(function (error) {
          window.dispatchEvent(new CustomEvent("app:backend-error", { detail: error }));
        });
      }
      render();
    },
    all: function () { return entries.slice(); },
    render: render
  };
  window.addEventListener("i18n:change", render);
}());
