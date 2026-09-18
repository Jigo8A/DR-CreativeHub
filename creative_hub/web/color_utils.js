(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.colorUtils = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function normalizeHexColor(value) {
    const digits = String(value || "").trim().replace(/^#/, "");
    return /^[0-9a-f]{6}$/i.test(digits) ? `#${digits.toUpperCase()}` : null;
  }

  return { normalizeHexColor };
});
