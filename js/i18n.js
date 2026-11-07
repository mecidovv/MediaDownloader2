(function () {
  "use strict";
  const dict = {};
  let lang = "tr";
  const LOC = { tr: "tr-TR", en: "en-US", ru: "ru-RU", de: "de-DE", it: "it-IT", ko: "ko-KR", zh: "zh-CN" };
  function fmt(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, k) { return params && params[k] !== undefined ? params[k] : m; });
  }
  function t(key, params) {
    const value = (dict[lang] && dict[lang][key]) || (dict.tr && dict.tr[key]) || key;
    return fmt(value, params);
  }
  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.dataset.i18n, el.dataset.n !== undefined ? { n: el.dataset.n } : null);
    });
    scope.querySelectorAll("[data-i18n-aria]").forEach(function (el) { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
    scope.querySelectorAll("[data-i18n-title]").forEach(function (el) { el.setAttribute("title", t(el.dataset.i18nTitle)); });
  }
  window.t = t;
  window.I18n = {
    add: function (code, entries) { dict[code] = entries; },
    languages: ["tr", "en", "ru", "de", "it", "ko", "zh"],
    locale: function () { return LOC[lang] || "tr-TR"; },
    get: function () { return lang; },
    apply: apply,
    setLanguage: function (code) {
      lang = dict[code] ? code : "tr";
      document.documentElement.lang = lang;
      apply();
      window.dispatchEvent(new CustomEvent("i18n:change", { detail: { lang: lang } }));
    }
  };
}());
