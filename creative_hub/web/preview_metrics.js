(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.previewMetrics = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  const VIDEO_WIDTH = 720;
  const ASS_OUTLINE = 3;
  const DEFAULT_STAGE_WIDTH = 310;

  function visibleStageWidth(stageWidth) {
    return Math.max(1, Number(stageWidth) || DEFAULT_STAGE_WIDTH);
  }

  function captionLayout() {
    return { width: "max-content", maxWidth: "none", whiteSpace: "nowrap" };
  }

  function captionMetrics(stageWidth, fontSize, outline = ASS_OUTLINE) {
    const scale = visibleStageWidth(stageWidth) / VIDEO_WIDTH;
    return {
      scale,
      fontSize: (Number(fontSize) || 0) * scale,
      outline: Math.max(0, Number(outline) || 0) * scale,
      shadow: 0,
    };
  }

  return { VIDEO_WIDTH, ASS_OUTLINE, visibleStageWidth, captionLayout, captionMetrics };
});
