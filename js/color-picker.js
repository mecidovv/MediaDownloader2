(function () {
  "use strict";

  function hslToHex(h, s, l) {
    s /= 100;
    l /= 100;
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs((h / 60) % 2 - 1));
    const m = l - c / 2;
    let rgb = [0, 0, 0];
    if (h < 60) rgb = [c, x, 0];
    else if (h < 120) rgb = [x, c, 0];
    else if (h < 180) rgb = [0, c, x];
    else if (h < 240) rgb = [0, x, c];
    else if (h < 300) rgb = [x, 0, c];
    else rgb = [c, 0, x];
    return "#" + rgb.map(function (channel) {
      return Math.round((channel + m) * 255).toString(16).padStart(2, "0");
    }).join("").toUpperCase();
  }

  function hexToRgb(hex) {
    const value = hex.replace("#", "");
    return [0, 2, 4].map(function (offset) { return parseInt(value.slice(offset, offset + 2), 16); });
  }

  function hexToHsl(hex) {
    const rgb = hexToRgb(hex).map(function (value) { return value / 255; });
    const max = Math.max.apply(null, rgb);
    const min = Math.min.apply(null, rgb);
    const delta = max - min;
    let hue = 0;
    const lightness = (max + min) / 2;
    let saturation = 0;
    if (delta) {
      saturation = delta / (1 - Math.abs(2 * lightness - 1));
      if (max === rgb[0]) hue = 60 * (((rgb[1] - rgb[2]) / delta) % 6);
      else if (max === rgb[1]) hue = 60 * ((rgb[2] - rgb[0]) / delta + 2);
      else hue = 60 * ((rgb[0] - rgb[1]) / delta + 4);
    }
    return { h: (hue + 360) % 360, s: saturation * 100, l: lightness * 100 };
  }

  function init() {
    const canvas = document.getElementById("colorWheel");
    if (!canvas) return;
    const context = canvas.getContext("2d");
    const swatch = document.getElementById("colorSwatch");
    const hexInput = document.getElementById("hexColor");
    const saturationInput = document.getElementById("colorSaturation");
    const lightnessInput = document.getElementById("colorLightness");
    const recentContainer = document.getElementById("recentColors");
    const radius = canvas.width / 2 - 5;
    let hsl = hexToHsl(AppSettings.get("accentColor"));
    let pointerDown = false;

    function renderWheel() {
      const image = context.createImageData(canvas.width, canvas.height);
      const center = canvas.width / 2;
      const hueSaturation = Number(saturationInput.value);
      const lightness = Number(lightnessInput.value);
      for (let y = 0; y < canvas.height; y++) {
        for (let x = 0; x < canvas.width; x++) {
          const dx = x - center;
          const dy = y - center;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance > radius) continue;
          const angle = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
          const color = hexToRgb(hslToHex(angle, Math.min(100, distance / radius * 100), lightness));
          const index = (y * canvas.width + x) * 4;
          image.data[index] = color[0];
          image.data[index + 1] = color[1];
          image.data[index + 2] = color[2];
          image.data[index + 3] = 255;
        }
      }
      context.putImageData(image, 0, 0);
      const markerRadius = radius * Math.min(1, hueSaturation / 100);
      const radians = hsl.h * Math.PI / 180;
      const markerX = center + Math.cos(radians) * markerRadius;
      const markerY = center + Math.sin(radians) * markerRadius;
      context.beginPath();
      context.arc(markerX, markerY, 8, 0, Math.PI * 2);
      context.fillStyle = hslToHex(hsl.h, hueSaturation, lightness);
      context.fill();
      context.lineWidth = 2.5;
      context.strokeStyle = "#fff";
      context.stroke();
    }

    function update(color, remember) {
      const normalized = color.toUpperCase();
      const rgb = hexToRgb(normalized);
      hsl = hexToHsl(normalized);
      saturationInput.value = String(Math.round(hsl.s));
      lightnessInput.value = String(Math.round(hsl.l));
      hexInput.value = normalized.slice(1);
      swatch.style.backgroundColor = normalized;
      document.querySelector('[data-output="colorSaturation"]').textContent = saturationInput.value + "%";
      document.querySelector('[data-output="colorLightness"]').textContent = lightnessInput.value + "%";
      document.documentElement.style.setProperty("--accent", normalized);
      document.documentElement.style.setProperty("--accent-strong", normalized);
      document.documentElement.style.setProperty("--accent-rgb", rgb.join(", "));
      AppSettings.set("accentColor", normalized);
      if (remember) rememberColor(normalized);
      renderWheel();
    }

    function rememberColor(color) {
      const recent = [color].concat(AppSettings.get("recentColors").filter(function (item) { return item !== color; })).slice(0, 8);
      AppSettings.set("recentColors", recent);
      renderRecentColors();
    }

    function renderRecentColors() {
      const colors = AppSettings.get("recentColors");
      recentContainer.replaceChildren();
      if (!colors.length) {
        const empty = document.createElement("span");
        empty.className = "muted-copy";
        empty.textContent = t("c.none");
        recentContainer.appendChild(empty);
        return;
      }
      colors.forEach(function (color) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "recent-color";
        button.style.backgroundColor = color;
        button.title = color;
        button.setAttribute("aria-label", t("c.pick", { c: color }));
        button.addEventListener("click", function () { update(color, false); });
        recentContainer.appendChild(button);
      });
    }

    function selectFromPointer(event, commit) {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const dx = (event.clientX - rect.left) * scaleX - canvas.width / 2;
      const dy = (event.clientY - rect.top) * scaleY - canvas.height / 2;
      const distance = Math.min(radius, Math.sqrt(dx * dx + dy * dy));
      hsl.h = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
      const saturation = Math.round(distance / radius * 100);
      saturationInput.value = String(saturation);
      update(hslToHex(hsl.h, saturation, Number(lightnessInput.value)), commit);
    }

    canvas.addEventListener("pointerdown", function (event) {
      pointerDown = true;
      canvas.setPointerCapture(event.pointerId);
      selectFromPointer(event, false);
    });
    canvas.addEventListener("pointermove", function (event) { if (pointerDown) selectFromPointer(event, false); });
    canvas.addEventListener("pointerup", function (event) {
      if (!pointerDown) return;
      pointerDown = false;
      selectFromPointer(event, true);
    });
    canvas.addEventListener("pointercancel", function () { pointerDown = false; });
    saturationInput.addEventListener("input", function () {
      update(hslToHex(hsl.h, Number(saturationInput.value), Number(lightnessInput.value)), false);
    });
    lightnessInput.addEventListener("input", function () {
      update(hslToHex(hsl.h, Number(saturationInput.value), Number(lightnessInput.value)), false);
    });
    document.getElementById("applyHex").addEventListener("click", function () {
      const value = hexInput.value.trim().replace(/^#/, "");
      if (!/^[\da-f]{6}$/i.test(value)) {
        window.dispatchEvent(new CustomEvent("app:toast", { detail: { message: t("c.bad"), type: "error" } }));
        return;
      }
      update("#" + value, true);
    });
    hexInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") document.getElementById("applyHex").click();
    });
    document.querySelectorAll(".color-preset").forEach(function (button) {
      button.style.backgroundColor = button.dataset.color;
      button.addEventListener("click", function () { update(button.dataset.color, true); });
    });
    AppSettings.onChange(function (key, value) {
      if (key === "accentColor" || key === "*") {
        const color = key === "*" ? AppSettings.get("accentColor") : value;
        const rgb = hexToRgb(color);
        document.documentElement.style.setProperty("--accent", color);
        document.documentElement.style.setProperty("--accent-strong", color);
        document.documentElement.style.setProperty("--accent-rgb", rgb.join(", "));
        hsl = hexToHsl(color);
        hexInput.value = color.slice(1);
        swatch.style.backgroundColor = color;
        saturationInput.value = String(Math.round(hsl.s));
        lightnessInput.value = String(Math.round(hsl.l));
        document.querySelector('[data-output="colorSaturation"]').textContent = saturationInput.value + "%";
        document.querySelector('[data-output="colorLightness"]').textContent = lightnessInput.value + "%";
        renderWheel();
      }
      if (key === "recentColors" || key === "*") renderRecentColors();
    });
    update(AppSettings.get("accentColor"), false);
    renderRecentColors();
  }

  window.ColorPicker = { init: init };
}());
