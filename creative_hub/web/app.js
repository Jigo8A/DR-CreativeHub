const views = {
  creative: { title: "Criativos", kicker: "WORKSPACE", action: "Nova copy", icon: "plus" },
  "headline-studio": { title: "Headlines", kicker: "WORKSPACE", action: "", icon: "network" },
  offers: { title: "Ofertas", kicker: "OPERACAO", action: "Nova oferta", icon: "folder-plus" },
  edit: { title: "Edicao", kicker: "MOTOR", action: "Salvar ajustes", icon: "save" },
  integrations: { title: "Integracoes e APIs", kicker: "CONFIGURACOES", action: "Salvar ajustes", icon: "save" },
  performance: { title: "Desempenho", kicker: "CONFIGURACOES", action: "Salvar ajustes", icon: "save" },
};

let state = { settings: {}, copies: [] };
let activeView = "creative";
let selectedIds = new Set();
let saveTimer;
let jobTimer;
let dragState;
let voiceLibrary = [];
let voiceConnection = "Conecte sua chave para carregar as vozes da conta.";
let headlineRenderTimer;
let headlinePreviewRequest = 0;
let headlinePreviewUrl = "";
let pickerOpen = false;
let offerModalMode = null;
let headlineStudioCopyId = "";
let headlineStudioDraft = null;
let nativeHeadlinePreviewTimer;
let nativeHeadlinePreviewUrl = "";
let nativeHeadlinePreviewRequest = 0;
let nativeHeadlineDragState;
let backgroundMusicPreview;
const copyTimers = new Map();
const pendingCopyPatches = new Map();
const SYSTEM_FONT_OPTIONS = [
  ["Roboto", "Roboto Regular"],
  ["Bahnschrift", "Bahnschrift"],
  ["Gadugi", "Gadugi"],
  ["Franklin Gothic Book", "Franklin Gothic Book"],
  ["Arial", "Arial"],
];
const HEADLINE_EMOJI_CATEGORIES = [
  ["Expressões", ["😀", "😂", "🥹", "😍", "🤩", "😱", "🤡", "🤔", "😎", "😭", "😡", "🤯"]],
  ["Gestos", ["👏", "🙌", "🙏", "💪", "👀", "👇", "👉", "🔥", "✨", "💯", "🚀", "🎯"]],
  ["Corações", ["❤️", "💛", "💚", "💙", "💜", "🩷", "🖤", "🤍", "💔", "💕", "💖", "💥"]],
  ["Objetos", ["🎁", "✅", "❌", "⚠️", "📌", "📚", "🎵", "🎉", "🛒", "💰", "⏰", "📲"]],
];

const $ = (selector, parent = document) => parent.querySelector(selector);
const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];

async function api(path, method = "GET", payload) {
  const response = await fetch(path, {
    method,
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Nao foi possivel concluir a acao.");
  return data;
}

async function loadState() {
  state = await api("/api/state");
  render();
  if (state.settings.voice_api_configured) loadVoices({ automatic: true });
}

function render() {
  renderCreativeView();
  renderHeadlineStudioView();
  renderOffersView();
  renderEditView();
  renderIntegrationsView();
  renderPerformanceView();
  showView(activeView);
  refreshIcons();
}

const NATIVE_HEADLINE_FIELDS = [
  "headline_text", "headline_duration", "headline_x_position", "headline_y_position",
  "headline_font_size", "headline_font_name", "headline_outline_enabled", "headline_outline_size",
  "headline_text_color", "headline_background_color", "headline_background_width",
  "headline_background_height", "headline_corner_radius",
];

function headlineStudioCopies() {
  const fromOffers = (state.offers || []).flatMap(offer => (offer.copies || []).map(copy => ({ ...copy, offer_name: offer.name })));
  return fromOffers.length ? fromOffers : (state.copies || []).map(copy => ({ ...copy, offer_name: state.active_offer?.name || "Oferta" }));
}

function nativeHeadlineDefaults(copy) {
  const base = Object.fromEntries(NATIVE_HEADLINE_FIELDS.map(key => [key, state.settings[key]]));
  return { ...base, ...(copy?.headline || {}), headline_text: copy?.headline?.headline_text || base.headline_text || "" };
}

function nativeHeadlineCopy() {
  const copies = headlineStudioCopies();
  return copies.find(copy => copy.id === headlineStudioCopyId) || copies.find(copy => copy.headline) || copies[0] || null;
}

function headlineEmojiButtons() {
  return HEADLINE_EMOJI_CATEGORIES.map(([label, emojis]) => `<section class="headline-emoji-category" aria-label="${label}"><span>${label}</span><div>${emojis.map(emoji => `<button type="button" class="headline-emoji-option" data-headline-emoji="${emoji}" aria-label="Inserir ${emoji}">${emoji}</button>`).join("")}</div></section>`).join("");
}

function renderHeadlineStudioView() {
  const target = $("#headlineStudioView");
  const copies = headlineStudioCopies();
  const active = nativeHeadlineCopy();
  if (!active) {
    target.innerHTML = `<div class="empty-state"><div class="empty-icon"><i data-lucide="type"></i></div><h2>Crie uma copy antes</h2><p>Assim que houver um criativo no workspace, ele aparecera aqui para receber uma headline individual.</p><button class="primary-button" id="headlineCreateCopy"><i data-lucide="plus"></i>Nova copy</button></div>`;
    $("#headlineCreateCopy", target).addEventListener("click", createCopy);
    return;
  }
  if (headlineStudioCopyId !== active.id) {
    headlineStudioCopyId = active.id;
    headlineStudioDraft = nativeHeadlineDefaults(active);
  }
  const draft = headlineStudioDraft || nativeHeadlineDefaults(active);
  const copyList = copies.map(copy => `<button class="headline-copy-item ${copy.id === active.id ? "active" : ""}" type="button" data-headline-copy="${escapeHtml(copy.id)}"><span class="headline-copy-title">${escapeHtml(copy.title || "Copy sem nome")}</span><span>${escapeHtml(copy.offer_name)}</span>${copy.headline ? `<i>Headline salva</i>` : ""}</button>`).join("");
  target.innerHTML = `<section class="native-headline-workspace"><aside class="headline-copy-catalog"><div class="headline-catalog-heading"><div><span class="field-label">CRIATIVOS</span><h2>Copies da operacao</h2></div><strong>${copies.length}</strong></div><div class="headline-copy-list">${copyList}</div></aside><section class="native-headline-editor"><div class="native-headline-editor-heading"><div><span class="field-label">HEADLINE INDIVIDUAL</span><h2>${escapeHtml(active.title || "Copy sem nome")}</h2><p>${escapeHtml(active.offer_name)}</p></div><div class="native-headline-actions"><button class="secondary-button" id="resetNativeHeadline" type="button"><i data-lucide="rotate-ccw"></i>Usar padrao</button>${active.headline ? `<button class="text-danger-button" id="removeNativeHeadline" type="button"><i data-lucide="trash-2"></i>Remover</button>` : ""}</div></div><div class="native-headline-form"><label class="native-headline-text"><span class="field-label">Texto da headline</span><textarea class="text-field native-headline-input" data-headline-field="headline_text" rows="5" placeholder="Escreva a headline. Cada quebra de linha sera mantida.">${escapeHtml(draft.headline_text || "")}</textarea></label><div class="field-grid three"><label><span class="field-label">Duracao (segundos)</span><input class="number-field native-headline-input" data-headline-field="headline_duration" type="number" min=".1" step=".1" value="${numberSetting(draft.headline_duration, 3)}"></label><label><span class="field-label">Fonte no video</span><input class="number-field native-headline-input" data-headline-field="headline_font_size" type="number" min="14" max="180" value="${numberSetting(draft.headline_font_size, 48)}"></label><label><span class="field-label">Fonte</span><select class="compact-select native-headline-input" data-headline-field="headline_font_name">${textFontOptions(draft.headline_font_name || "Uninsta Heavy")}</select></label><label><span class="field-label">Cor do texto</span><input class="color-field native-headline-input" data-headline-field="headline_text_color" type="color" value="${escapeHtml(colorUtils.normalizeHexColor(draft.headline_text_color) || "#FFFFFF")}"></label><label><span class="field-label">Cor do fundo</span><input class="color-field native-headline-input" data-headline-field="headline_background_color" type="color" value="${escapeHtml(colorUtils.normalizeHexColor(draft.headline_background_color) || "#E31B14")}"></label><label class="toggle-row"><input class="native-headline-input" data-headline-field="headline_outline_enabled" type="checkbox" ${draft.headline_outline_enabled ? "checked" : ""}>Contorno preto</label><label><span class="field-label">Espessura do contorno</span><input class="number-field native-headline-input" data-headline-field="headline_outline_size" type="number" min="0" max="12" value="${numberSetting(draft.headline_outline_size, 0)}"></label><label><span class="field-label">Largura do fundo</span><input class="number-field native-headline-input" data-headline-field="headline_background_width" type="number" min="40" max="720" value="${numberSetting(draft.headline_background_width, 520)}"></label><label><span class="field-label">Altura do fundo</span><input class="number-field native-headline-input" data-headline-field="headline_background_height" type="number" min="30" max="600" value="${numberSetting(draft.headline_background_height, 140)}"></label><label><span class="field-label">Cantos arredondados</span><input class="number-field native-headline-input" data-headline-field="headline_corner_radius" type="number" min="0" max="180" value="${numberSetting(draft.headline_corner_radius, 16)}"></label><label><span class="field-label">Posicao X (%)</span><input class="number-field native-headline-input" data-percent="true" data-headline-field="headline_x_position" type="number" min="0" max="100" value="${Math.round(numberSetting(draft.headline_x_position, .5) * 100)}"></label><label><span class="field-label">Posicao Y (%)</span><input class="number-field native-headline-input" data-percent="true" data-headline-field="headline_y_position" type="number" min="0" max="100" value="${Math.round(numberSetting(draft.headline_y_position, .2) * 100)}"></label></div></div><div class="native-headline-savebar"><span>As alteracoes desta tela pertencem somente a esta copy.</span><button class="primary-button" id="saveNativeHeadline" type="button"><i data-lucide="save"></i>Salvar headline desta copy</button></div></section><aside class="native-headline-preview"><div><span class="field-label">PREVIEW EXATO</span><h2>Video 9:16</h2><p>Renderizado pelo mesmo motor do video final.</p></div><div class="native-headline-stage"><div class="native-headline-scene"></div><img id="nativeHeadlineRender" alt="Previa da headline"></div><div class="native-headline-preview-values"><span>${Math.round(numberSetting(draft.headline_x_position, .5) * 100)}% X</span><span>${Math.round(numberSetting(draft.headline_y_position, .2) * 100)}% Y</span><span>${numberSetting(draft.headline_font_size, 48)}px</span></div></aside></section>`;
  mountNativeHeadlineInteraction(target);
  $$("[data-headline-copy]", target).forEach(button => button.addEventListener("click", () => {
    headlineStudioCopyId = button.dataset.headlineCopy;
    const next = headlineStudioCopies().find(copy => copy.id === headlineStudioCopyId);
    headlineStudioDraft = nativeHeadlineDefaults(next);
    renderHeadlineStudioView();
    refreshIcons();
  }));
  $$(".native-headline-input", target).forEach(input => input.addEventListener("input", updateNativeHeadlineDraft));
  $$(".native-headline-input", target).forEach(input => input.addEventListener("change", updateNativeHeadlineDraft));
  $("#resetNativeHeadline", target).addEventListener("click", () => { headlineStudioDraft = nativeHeadlineDefaults({}); renderHeadlineStudioView(); refreshIcons(); });
  $("#removeNativeHeadline", target)?.addEventListener("click", removeNativeHeadline);
  $("#saveNativeHeadline", target).addEventListener("click", saveNativeHeadline);
  scheduleNativeHeadlinePreview();
}

function bindHeadlineEmojiPicker(target) {
  const toggle = $("#headlineEmojiPickerToggle", target);
  const picker = $("#headlineEmojiPicker", target);
  const input = $("[data-headline-field=\"headline_text\"]", target);
  if (!toggle || !picker || !input) return;
  toggle.addEventListener("click", () => {
    const isOpen = picker.hasAttribute("hidden");
    picker.toggleAttribute("hidden", !isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
  });
  $$('[data-headline-emoji]', picker).forEach(button => button.addEventListener("click", () => insertHeadlineEmoji(input, button.dataset.headlineEmoji, picker, toggle)));
}

function insertHeadlineEmoji(input, emoji, picker, toggle) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? start;
  input.value = `${input.value.slice(0, start)}${emoji}${input.value.slice(end)}`;
  input.selectionStart = input.selectionEnd = start + emoji.length;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  picker.setAttribute("hidden", "");
  toggle.setAttribute("aria-expanded", "false");
  input.focus();
}

function mountNativeHeadlineInteraction(target) {
  const stage = $(".native-headline-stage", target);
  if (!stage) return;
  stage.insertAdjacentHTML("beforeend", `<div class="native-headline-guides" aria-hidden="true"><i class="native-preview-guide vertical" id="nativeHeadlineVerticalGuide"></i><i class="native-preview-guide horizontal" id="nativeHeadlineHorizontalGuide"></i></div><div class="native-headline-hitbox" id="nativeHeadlineHitbox" aria-label="Mover ou redimensionar headline"><i class="native-headline-handle width" id="nativeHeadlineWidthHandle" title="Ajustar largura"></i><i class="native-headline-handle height" id="nativeHeadlineHeightHandle" title="Ajustar altura"></i><i class="native-headline-handle corner" id="nativeHeadlineCornerHandle" title="Ajustar largura e altura"></i></div>`);
  bindNativeHeadlinePreview();
  syncNativeHeadlineInteraction();
}

function bindNativeHeadlinePreview() {
  const stage = $(".native-headline-stage");
  const hitbox = $("#nativeHeadlineHitbox");
  if (!stage || !hitbox) return;
  hitbox.addEventListener("pointerdown", event => {
    if (event.target.classList.contains("native-headline-handle")) return;
    event.preventDefault();
    beginNativeHeadlineInteraction(event, hitbox, { mode: "move", pointerId: event.pointerId, stage });
  });
  bindNativeHeadlineResizeHandle($("#nativeHeadlineWidthHandle"), "resize-width", stage);
  bindNativeHeadlineResizeHandle($("#nativeHeadlineHeightHandle"), "resize-height", stage);
  bindNativeHeadlineResizeHandle($("#nativeHeadlineCornerHandle"), "resize-both", stage);
}

function bindNativeHeadlineResizeHandle(handle, mode, stage) {
  handle?.addEventListener("pointerdown", event => {
    event.preventDefault();
    event.stopPropagation();
    beginNativeHeadlineInteraction(event, handle, {
      mode,
      pointerId: event.pointerId,
      stage,
      startX: event.clientX,
      startY: event.clientY,
      startWidth: numberSetting(headlineStudioDraft?.headline_background_width, 520),
      startHeight: numberSetting(headlineStudioDraft?.headline_background_height, 140),
      startHeadlineX: numberSetting(headlineStudioDraft?.headline_x_position, .5),
      startHeadlineY: numberSetting(headlineStudioDraft?.headline_y_position, .2),
    });
  });
}

function beginNativeHeadlineInteraction(event, target, nextState) {
  nativeHeadlineDragState = nextState;
  target.setPointerCapture?.(event.pointerId);
  window.addEventListener("pointermove", moveNativeHeadlinePreview);
  window.addEventListener("pointerup", endNativeHeadlinePreview, { once: true });
}

function moveNativeHeadlinePreview(event) {
  if (!nativeHeadlineDragState || !headlineStudioDraft) return;
  const rect = nativeHeadlineDragState.stage.getBoundingClientRect();
  if (nativeHeadlineDragState.mode === "move") {
    const x = snapToCenter(clamp((event.clientX - rect.left) / rect.width, 0, 1));
    const y = snapToCenter(clamp((event.clientY - rect.top) / rect.height, 0, 1));
    headlineStudioDraft = { ...headlineStudioDraft, headline_x_position: x.value, headline_y_position: y.value };
    setNativeHeadlineGuides(x.snapped, y.snapped);
  } else {
    resizeNativeHeadlinePreview(event, rect);
  }
  syncNativeHeadlineInteraction();
  syncNativeHeadlineInputs();
  scheduleNativeHeadlinePreview();
}

function resizeNativeHeadlinePreview(event, rect) {
  const scale = previewMetrics.captionMetrics(rect.width, 1).scale || 1;
  const resizeWidth = nativeHeadlineDragState.mode === "resize-width" || nativeHeadlineDragState.mode === "resize-both";
  const resizeHeight = nativeHeadlineDragState.mode === "resize-height" || nativeHeadlineDragState.mode === "resize-both";
  const next = { ...headlineStudioDraft };
  if (resizeWidth) {
    const startLeft = nativeHeadlineDragState.startHeadlineX * 720 - nativeHeadlineDragState.startWidth / 2;
    const width = clamp(Math.round(nativeHeadlineDragState.startWidth + (event.clientX - nativeHeadlineDragState.startX) / scale), 40, Math.max(40, 720 - startLeft));
    next.headline_background_width = width;
    next.headline_x_position = clamp((startLeft + width / 2) / 720, 0, 1);
  }
  if (resizeHeight) {
    const startTop = nativeHeadlineDragState.startHeadlineY * 1280 - nativeHeadlineDragState.startHeight / 2;
    const height = clamp(Math.round(nativeHeadlineDragState.startHeight + (event.clientY - nativeHeadlineDragState.startY) / scale), 40, Math.max(40, 1280 - startTop));
    next.headline_background_height = height;
    next.headline_y_position = clamp((startTop + height / 2) / 1280, 0, 1);
  }
  headlineStudioDraft = next;
}

function endNativeHeadlinePreview() {
  nativeHeadlineDragState = null;
  window.removeEventListener("pointermove", moveNativeHeadlinePreview);
  setNativeHeadlineGuides(false, false);
}

function setNativeHeadlineGuides(showVertical, showHorizontal) {
  $("#nativeHeadlineVerticalGuide")?.classList.toggle("visible", showVertical);
  $("#nativeHeadlineHorizontalGuide")?.classList.toggle("visible", showHorizontal);
}

function syncNativeHeadlineInputs() {
  $$(".native-headline-input").forEach(input => {
    const key = input.dataset.headlineField;
    let value = headlineStudioDraft?.[key];
    if (input.type === "checkbox") input.checked = Boolean(value);
    else {
      if (input.dataset.percent === "true") value = Math.round(numberSetting(value, .5) * 100);
      input.value = value ?? "";
    }
  });
}

function syncNativeHeadlineInteraction() {
  const stage = $(".native-headline-stage");
  const hitbox = $("#nativeHeadlineHitbox");
  if (!stage || !hitbox || !headlineStudioDraft) return;
  const scale = previewMetrics.captionMetrics(stage.clientWidth, 1).scale || 1;
  const x = numberSetting(headlineStudioDraft.headline_x_position, .5);
  const y = numberSetting(headlineStudioDraft.headline_y_position, .2);
  hitbox.style.left = `${x * 100}%`;
  hitbox.style.top = `${y * 100}%`;
  hitbox.style.width = `${numberSetting(headlineStudioDraft.headline_background_width, 520) * scale}px`;
  hitbox.style.height = `${numberSetting(headlineStudioDraft.headline_background_height, 140) * scale}px`;
  hitbox.style.borderRadius = `${numberSetting(headlineStudioDraft.headline_corner_radius, 16) * scale}px`;
  hitbox.classList.toggle("has-outline", Boolean(headlineStudioDraft.headline_outline_enabled) && numberSetting(headlineStudioDraft.headline_outline_size, 0) > 0);
  const values = $$(".native-headline-preview-values span");
  if (values.length === 3) {
    values[0].textContent = `${Math.round(x * 100)}% X`;
    values[1].textContent = `${Math.round(y * 100)}% Y`;
    values[2].textContent = `${numberSetting(headlineStudioDraft.headline_font_size, 48)}px`;
  }
}

function updateNativeHeadlineDraft(event) {
  const input = event.currentTarget;
  const key = input.dataset.headlineField;
  let value = input.type === "checkbox" ? input.checked : input.value;
  if (input.dataset.percent === "true") value = Number(value) / 100;
  else if (input.type === "number") value = Number(value);
  headlineStudioDraft = { ...headlineStudioDraft, [key]: value };
  syncNativeHeadlineInteraction();
  scheduleNativeHeadlinePreview();
}

function scheduleNativeHeadlinePreview() {
  clearTimeout(nativeHeadlinePreviewTimer);
  nativeHeadlinePreviewTimer = setTimeout(loadNativeHeadlinePreview, 220);
}

async function loadNativeHeadlinePreview() {
  const image = $("#nativeHeadlineRender");
  if (!image || !headlineStudioDraft?.headline_text?.trim()) return;
  const requestId = ++nativeHeadlinePreviewRequest;
  try {
    const response = await fetch("/api/headline-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...headlineStudioDraft, headline_enabled: true }) });
    if (!response.ok || requestId !== nativeHeadlinePreviewRequest) return;
    const url = URL.createObjectURL(await response.blob());
    if (nativeHeadlinePreviewUrl) URL.revokeObjectURL(nativeHeadlinePreviewUrl);
    nativeHeadlinePreviewUrl = url;
    image.src = url;
  } catch (_) { /* The form remains editable if preview rendering is unavailable. */ }
}

async function saveNativeHeadline() {
  try {
    const result = await api(`/api/copies/${encodeURIComponent(headlineStudioCopyId)}`, "PUT", { headline: headlineStudioDraft });
    headlineStudioDraft = nativeHeadlineDefaults(result.copy);
    showToast("Headline individual salva nesta copy.");
    await loadState();
  } catch (error) { showError(error); }
}

async function removeNativeHeadline() {
  try {
    await api(`/api/copies/${encodeURIComponent(headlineStudioCopyId)}`, "PUT", { headline: null });
    headlineStudioDraft = nativeHeadlineDefaults({});
    showToast("Headline individual removida.");
    await loadState();
  } catch (error) { showError(error); }
}

function renderCreativeView() {
  const target = $("#creativeView");
  const workspace = offerWorkspaceHtml();
  if (!state.copies.length) {
    const manualImport = state.active_offer?.manual_audio_inbox_folder ? `<button class="secondary-button" id="importManualAudio"><i data-lucide="audio-lines"></i>Importar audios manuais</button>` : "";
    target.innerHTML = `${workspace}<div class="empty-state"><div class="empty-icon"><i data-lucide="file-plus-2"></i></div><h2>Comece pelas copies</h2><p>Crie um card para cada anuncio. A central guarda seus textos, audios e resultados em um so lugar.</p><div class="empty-state-actions">${manualImport}<button class="primary-button" id="createFirstCopy"><i data-lucide="plus"></i>Criar primeira copy</button></div></div>`;
    bindOfferWorkspace(target);
    $("#importManualAudio", target)?.addEventListener("click", importManualAudio);
    $("#createFirstCopy", target).addEventListener("click", createCopy);
    return;
  }
  const allSelected = state.copies.length > 0 && state.copies.every(copy => selectedIds.has(copy.id));
  const manualImport = state.active_offer?.manual_audio_inbox_folder ? `<button class="secondary-button" id="importManualAudio"><i data-lucide="audio-lines"></i>Importar audios manuais</button>` : "";
  target.innerHTML = `<section class="batch-toolbar"><div><span class="field-label">PRODUCAO</span><h2>Escolha o que deseja gerar</h2><p>As caixas de selecao abaixo servem apenas para gerar audio ou testar uma copy.</p></div><div class="batch-actions"><button class="secondary-button" id="renderActiveOffer"><i data-lucide="play"></i>Gerar esta oferta</button><button class="primary-button" id="renderAllOffers"><i data-lucide="layers-3"></i>Gerar todas as ofertas</button></div></section>${workspace}<div class="toolbar offer-toolbar"><div><h2>${state.copies.length} ${state.copies.length === 1 ? "copy" : "copies"} nesta oferta</h2><p>Selecione somente o que deseja gerar audio ou testar nesta aba.</p></div><div class="toolbar-actions">${manualImport}<button class="secondary-button" id="toggleAllCopies" aria-pressed="${allSelected}"><i data-lucide="check-check"></i>${allSelected ? "Desmarcar todas desta aba" : "Selecionar todas desta aba"}</button><button class="secondary-button" id="generateVoice"><i data-lucide="mic"></i>Gerar audios selecionados</button><button class="secondary-button" id="renderTest"><i data-lucide="flask-conical"></i>Testar selecionado</button><button class="primary-button" id="createCopyInWorkspace"><i data-lucide="plus"></i>Nova copy</button></div></div><div class="cards-list">${state.copies.map(copyCardHtml).join("")}</div>`;
  bindOfferWorkspace(target);
  $("#toggleAllCopies", target).addEventListener("click", toggleAllCopies);
  $("#generateVoice", target).addEventListener("click", startVoiceGeneration);
  $("#renderTest", target).addEventListener("click", () => startProduction("test"));
  $("#createCopyInWorkspace", target).addEventListener("click", createCopy);
  $("#importManualAudio", target)?.addEventListener("click", importManualAudio);
  $("#renderActiveOffer", target).addEventListener("click", () => openBatchSetup("active"));
  $("#renderAllOffers", target).addEventListener("click", () => openBatchSetup("all"));
  $$(".creative-card", target).forEach(bindCard);
}

function offerWorkspaceHtml() {
  const active = state.active_offer || {};
  const tabs = (state.offers || []).map(offer => `<button class="offer-tab ${offer.id === state.active_offer_id ? "active" : ""}" type="button" role="tab" aria-selected="${offer.id === state.active_offer_id}" data-offer-id="${escapeHtml(offer.id)}"><i data-lucide="layers-2"></i><span>${escapeHtml(offer.name)}</span></button>`).join("");
  return `<section class="offer-workspace"><div class="offer-tabs" role="tablist" aria-label="Ofertas no workspace">${tabs}<button class="offer-tab-add" id="createOffer" type="button" aria-label="Nova oferta" title="Nova oferta"><i data-lucide="plus"></i></button></div><div class="offer-media-status"><i data-lucide="folder-check"></i><span>${active.takes_folder ? "Midias vinculadas" : "Configure as midias em Ofertas"}</span><button class="secondary-button compact-headline-link" id="openHeadlineStudio" type="button"><i data-lucide="network"></i>Abrir headlines</button></div></section>`;
}

function bindOfferWorkspace(target) {
  $$(".offer-tab", target).forEach(button => button.addEventListener("click", () => activateOffer(button.dataset.offerId)));
  $("#createOffer", target)?.addEventListener("click", createOffer);
  $("#openHeadlineStudio", target)?.addEventListener("click", () => showView("headline-studio"));
}

function renderOffersView() {
  const target = $("#offersView");
  const offer = state.active_offer || {};
  const catalog = (state.offers || []).map(item => `<button class="offer-catalog-item ${item.id === state.active_offer_id ? "active" : ""}" type="button" data-offer-id="${escapeHtml(item.id)}"><i data-lucide="package"></i><span>${escapeHtml(item.name)}</span><i class="catalog-arrow" data-lucide="chevron-right"></i></button>`).join("");
  const canDelete = (state.offers || []).length > 1;
  target.innerHTML = `<div class="offers-page"><section class="settings-group central-folder"><h3>Central de ofertas</h3><p class="provider-note">As novas ofertas serao criadas diretamente dentro desta pasta.</p><div class="field-grid"><div class="wide-field">${folderInput("creative_root_folder", "Pasta central da operacao", state.settings.creative_root_folder)}</div></div></section><div class="offers-manager"><aside class="offer-catalog"><div class="catalog-heading"><div><h3>Catalogo</h3><span>${(state.offers || []).length} ${(state.offers || []).length === 1 ? "oferta" : "ofertas"}</span></div><button class="icon-button" id="createOfferFromOffers" type="button" aria-label="Nova oferta" title="Nova oferta"><i data-lucide="plus"></i></button></div><div class="catalog-list">${catalog}</div></aside><section class="offer-details"><div class="offer-details-heading"><div><span class="detail-icon"><i data-lucide="package-open"></i></span><div><h2>${escapeHtml(offer.name || "Oferta")}</h2><p>Configuracoes de midia desta oferta.</p></div></div>${canDelete ? `<button class="text-danger-button" id="deleteOffer" type="button"><i data-lucide="trash-2"></i>Excluir oferta</button>` : ""}</div><div class="offer-details-grid"><div class="wide-field">${offerFolderInput("takes_folder", "Pasta de takes", offer.takes_folder)}</div><div class="wide-field">${offerFileInput("broll_path", "Video de B-roll", offer.broll_path)}</div><div class="wide-field">${offerFolderInput("api_audio_folder", "Pasta de audios API", offer.api_audio_folder)}</div><div class="wide-field">${offerFolderInput("manual_audio_inbox_folder", "Entrada de audios manuais", offer.manual_audio_inbox_folder)}</div><div class="wide-field">${offerFolderInput("manual_audio_library_folder", "Biblioteca de audios manuais", offer.manual_audio_library_folder)}</div><div class="wide-field">${offerFolderInput("output_folder", "Pasta de output", offer.output_folder)}</div><div class="wide-field">${musicRuleControls("offer-input", offer, false)}</div></div></section></div></div>`;
  bindOfferInputs(target, offer.id);
  $("#createOfferFromOffers", target).addEventListener("click", openCreateOfferModal);
  $("#deleteOffer", target)?.addEventListener("click", () => openDeleteOfferModal(offer));
  $$(".offer-catalog-item", target).forEach(button => button.addEventListener("click", () => activateOffer(button.dataset.offerId)));
}

function renderTranscriptionControl(settings) {
  const provider = settings.transcription_provider || "local";
  const connected = Boolean(settings.assemblyai_api_configured);
  const status = connected ? "AssemblyAI configurada" : "AssemblyAI nao configurada";
  const badge = `<span class="connection-status ${connected ? "connected" : ""}">${connected ? '<i data-lucide="circle-check"></i>' : '<i data-lucide="circle-alert"></i>'}${status}</span>`;
  return `<section class="settings-group"><div class="settings-heading"><div><h3>Transcricao</h3><p class="provider-note">Escolha entre Whisper local ou AssemblyAI para gerar legendas.</p></div>${badge}</div><div class="field-grid"><label><span class="field-label">Motor de transcricao</span><select class="compact-select setting-input" data-setting="transcription_provider"><option value="local" ${provider === "local" ? "selected" : ""}>Whisper local</option><option value="assemblyai" ${provider === "assemblyai" ? "selected" : ""}>AssemblyAI</option></select></label>${!connected ? `<div class="api-setup-action"><button class="secondary-button" id="goToIntegrations" type="button"><i data-lucide="plug-zap"></i>Configurar API</button></div>` : ""}${provider === "assemblyai" ? `<label><span class="field-label">Modelo</span><input class="text-field" value="Universal-3.5 Pro" disabled></label>` : ""}</div></section>`;
}

function copyCardHtml(copy) {
  const selected = selectedIds.has(copy.id) ? "checked" : "";
  const status = copy.status || "draft";
  const readableStatus = { draft: "Rascunho", audio_ready: "Audio pronto", rendered: "Renderizado", error: "Erro" }[status] || status;
  return `<article class="creative-card" data-copy-id="${copy.id}">
    <div class="card-selection"><input class="check select-copy" type="checkbox" ${selected} aria-label="Selecionar criativo"></div>
    <div class="card-main"><div class="card-heading"><input class="copy-title" value="${escapeHtml(copy.title)}" placeholder="Titulo da copy"><span class="status-chip ${status}">${readableStatus}</span></div><textarea class="copy-text" placeholder="Escreva a copy que sera narrada...">${escapeHtml(copy.text)}</textarea>${copy.error ? `<p class="card-error">${escapeHtml(copy.error)}</p>` : ""}</div>
    <div class="card-side"><div><label class="field-label">Origem do audio</label><select class="compact-select audio-source"><option value="api" ${copy.audio_source === "api" ? "selected" : ""}>Gerar por API</option><option value="manual" ${copy.audio_source === "manual" ? "selected" : ""}>Audio manual</option></select></div>${copy.audio_source === "manual" ? manualAudioControl(copy) : apiVoiceControl(copy)}${musicRuleControls("copy-music-input", copy, true)}<div class="card-actions"><button class="icon-button duplicate-copy" type="button" aria-label="Duplicar copy" title="Duplicar copy"><i data-lucide="copy"></i></button><button class="icon-button delete-copy danger" type="button" aria-label="Excluir copy" title="Excluir copy"><i data-lucide="trash-2"></i></button>${copy.output_path ? `<button class="icon-button open-video" type="button" data-video="${escapeHtml(copy.output_path)}" aria-label="Abrir video" title="Abrir video"><i data-lucide="square-play"></i></button>` : ""}</div></div>
  </article>`;
}

function musicRuleControls(className, rule, allowInherit) {
  const library = state.music_library || {};
  const mode = rule.background_music_mode || (allowInherit ? "inherit" : "none");
  const categories = Object.keys(library);
  const categoryOptions = categories.map(category => `<option value="${escapeHtml(category)}" ${category === rule.background_music_category ? "selected" : ""}>${escapeHtml(category)}</option>`).join("");
  const tracks = library[rule.background_music_category] || [];
  const trackOptions = tracks.map(track => `<option value="${escapeHtml(track.path)}" ${track.path === rule.background_music_track_path ? "selected" : ""}>${escapeHtml(track.name)}</option>`).join("");
  const field = className === "offer-input" ? "data-offer-field" : "data-copy-music-field";
  const modeAttribute = className === "offer-input" ? "data-offer-music-mode" : "data-copy-music-mode";
  const isCustom = mode === "track" || mode === "category";
  const button = (value, label, icon, active) => `<button class="music-mode-button ${active ? "active" : ""}" type="button" ${modeAttribute}="${value}" aria-pressed="${active}"><i data-lucide="${icon}"></i><span>${label}</span></button>`;
  const selectedTrack = tracks.find(track => track.path === rule.background_music_track_path);
  const categoryControl = `<label><span class="field-label">Categoria</span><select class="compact-select ${className}" ${field}="background_music_category"><option value="">Selecione a categoria</option>${categoryOptions}</select></label>`;
  const trackControl = `<label><span class="field-label">Musica</span><div class="music-track-row"><select class="compact-select ${className}" ${field}="background_music_track_path"><option value="">Selecione a musica</option>${trackOptions}</select>${selectedTrack ? `<button class="mini-button music-preview-track" type="button" data-music-preview="${escapeHtml(selectedTrack.path)}" aria-label="Ouvir ${escapeHtml(selectedTrack.name)}" title="Ouvir musica"><i data-lucide="play"></i></button>` : ""}</div></label>`;
  if (!allowInherit) {
    return `<div class="music-rule"><span class="field-label">Musica de fundo</span><div class="music-mode-switch" role="group" aria-label="Modo de musica">${button("none", "Sem musica", "volume-x", mode === "none")}${button("category", "Sortear categoria", "shuffle", mode === "category")}${button("track", "Escolher musica", "music-2", mode === "track")}</div>${mode === "category" ? categoryControl : ""}${mode === "track" ? `${categoryControl}${trackControl}` : ""}</div>`;
  }
  const inheritedRule = state.active_offer || {};
  const inheritedSummary = inheritedRule.background_music_mode === "category" ? `Sorteio pela categoria ${inheritedRule.background_music_category || "nao definida"}` : inheritedRule.background_music_mode === "track" ? `Faixa: ${(inheritedRule.background_music_track_path || "").split(/[\\/]/).pop() || "nao definida"}` : "A oferta esta configurada sem musica";
  return `<div class="music-rule"><span class="field-label">Musica de fundo</span><div class="music-mode-switch" role="group" aria-label="Modo de musica desta copy">${button("none", "Sem musica", "volume-x", mode === "none")}${button("inherit", "Padrao da oferta", "layers-3", mode === "inherit")}${button("category", "Personalizar", "sliders-horizontal", isCustom)}</div>${mode === "inherit" ? `<div class="music-inherit-summary"><i data-lucide="layers-3"></i><span>${escapeHtml(inheritedSummary)}</span><button class="music-edit-offer" type="button">Editar oferta</button></div>` : ""}${isCustom ? `<div class="music-custom-mode" role="group" aria-label="Tipo de musica personalizada">${button("category", "Sortear por categoria", "shuffle", mode === "category")}${button("track", "Musica especifica", "music-2", mode === "track")}</div>${categoryControl}${mode === "track" ? trackControl : ""}` : ""}</div>`;
}

function previewBackgroundMusic(path, button) {
  if (!path) return;
  if (backgroundMusicPreview?.dataset.path === path) {
    backgroundMusicPreview.paused ? backgroundMusicPreview.play() : backgroundMusicPreview.pause();
    return;
  }
  backgroundMusicPreview?.pause();
  $$(".music-preview-track.playing").forEach(item => item.classList.remove("playing"));
  const audio = new Audio(`/api/music?path=${encodeURIComponent(path)}`);
  audio.dataset.path = path;
  audio.addEventListener("play", () => button.classList.add("playing"));
  audio.addEventListener("pause", () => button.classList.remove("playing"));
  audio.addEventListener("ended", () => button.classList.remove("playing"));
  backgroundMusicPreview = audio;
  audio.play().catch(showError);
}

function manualAudioControl(copy) { return `<div><label class="field-label">Arquivo de audio</label><div class="audio-row"><input class="text-field audio-path" value="${escapeHtml(copy.audio_path || "")}" placeholder="Caminho do audio"><button class="mini-button attach-audio" type="button" aria-label="Vincular audio" title="Vincular audio"><i data-lucide="link"></i></button></div></div>`; }
function apiVoiceControl(copy) { return `<div><label class="field-label">Voz da narracao</label><select class="compact-select card-voice">${voiceOptions(copy.voice_name, true)}</select></div>`; }
function voiceOptions(selected, allowDefault = false) { const defaultLabel = state.settings.voice_name ? `Usar voz padrao: ${voiceLabel(state.settings.voice_name)}` : "Usar voz padrao"; const initial = allowDefault ? `<option value="" ${selected ? "" : "selected"}>${escapeHtml(defaultLabel)}</option>` : ""; if (!voiceLibrary.length) return `${initial}<option value="" disabled ${selected ? "" : "selected"}>Carregue as vozes em Configuracoes</option>`; return initial + voiceLibrary.map(voice => `<option value="${escapeHtml(voice.id)}" ${voice.id === selected ? "selected" : ""}>${escapeHtml(voice.name)}${voice.language ? ` - ${escapeHtml(voice.language)}` : ""}</option>`).join(""); }
function voiceLabel(id) { return voiceLibrary.find(voice => voice.id === id)?.name || id; }
function textFontOptions(selected) {
  const localFonts = (state.available_fonts || []).map(name => [name, name]);
  const options = [...localFonts, ...SYSTEM_FONT_OPTIONS];
  if (selected && !options.some(([value]) => value === selected)) options.unshift([selected, selected]);
  return options.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
}
function colorControl(setting, label, value) { const normalized = colorUtils.normalizeHexColor(value) || "#FFEF00"; return `<div class="color-control"><span class="field-label">${escapeHtml(label)}</span><div class="color-control-row"><input class="color-field setting-input" data-setting="${setting}" type="color" value="${normalized}"><button class="hex-toggle" type="button" aria-expanded="false" title="Inserir codigo HEX">Hex<i data-lucide="chevron-down"></i></button></div><div class="hex-entry"><span>#</span><input class="hex-input" data-setting="${setting}" value="${normalized.slice(1)}" inputmode="text" maxlength="6" autocomplete="off" aria-label="Codigo HEX"></div></div>`; }

function bindCard(cardElement) {
  const id = cardElement.dataset.copyId;
  $(".select-copy", cardElement).addEventListener("change", event => {
    event.target.checked ? selectedIds.add(id) : selectedIds.delete(id);
  });
  $(".copy-title", cardElement).addEventListener("input", event => scheduleCopyUpdate(id, { title: event.target.value }));
  $(".copy-text", cardElement).addEventListener("input", event => scheduleCopyUpdate(id, { text: event.target.value }));
  $(".audio-source", cardElement).addEventListener("change", event => updateCopy(id, { audio_source: event.target.value }, true));
  const voice = $(".card-voice", cardElement);
  if (voice) voice.addEventListener("change", event => updateCopy(id, { voice_name: event.target.value }));
  $$(".copy-music-input", cardElement).forEach(input => input.addEventListener("change", event => updateCopy(id, { [event.target.dataset.copyMusicField]: event.target.value }, true)));
  $$("[data-copy-music-mode]", cardElement).forEach(button => button.addEventListener("click", () => updateCopy(id, { background_music_mode: button.dataset.copyMusicMode }, true)));
  $$(".music-preview-track", cardElement).forEach(button => button.addEventListener("click", () => previewBackgroundMusic(button.dataset.musicPreview, button)));
  $(".music-edit-offer", cardElement)?.addEventListener("click", () => showView("offers"));
  const attach = $(".attach-audio", cardElement);
  if (attach) attach.addEventListener("click", () => attachAudio(id, $(".audio-path", cardElement).value));
  $(".duplicate-copy", cardElement).addEventListener("click", () => duplicateCopy(id));
  $(".delete-copy", cardElement).addEventListener("click", () => deleteCopy(id));
  const openVideo = $(".open-video", cardElement);
  if (openVideo) openVideo.addEventListener("click", () => openVideoPlayer(openVideo.dataset.video));
}

function renderEditView() {
  const s = state.settings;
  $("#editView").innerHTML = `<div class="edit-layout"><div class="settings-stack">
    <section class="settings-group"><h3>Montagem</h3><div class="field-grid"><label><span class="field-label">Duracao de cada take</span><input class="number-field setting-input" data-setting="segment_duration" type="number" min=".5" step=".1" value="${s.segment_duration}"></label><label><span class="field-label">Velocidade dos takes</span><input class="number-field setting-input" data-setting="background_speed" type="number" min=".1" max="3" step=".05" value="${s.background_speed}"></label><label class="toggle-row wide-field"><input class="setting-input" data-setting="speed_broll" type="checkbox" ${s.speed_broll ? "checked" : ""}>Aplicar a mesma velocidade ao B-roll</label><label class="wide-field"><span class="field-label">Palavras-chave do B-roll</span><input class="text-field setting-input" data-setting="broll_keywords" value="${escapeHtml(s.broll_keywords || "")}" placeholder="dinamica, dinamicas, dinâmica"></label></div></section>
    ${renderTranscriptionControl(s)}
    <section class="settings-group"><h3>Tratamento do audio</h3><div class="field-grid three"><label class="toggle-row"><input class="setting-input" data-setting="trim_audio_edges" type="checkbox" ${s.trim_audio_edges ? "checked" : ""}>Cortar inicio e fim</label><label class="toggle-row"><input class="setting-input" data-setting="cut_internal_silence" type="checkbox" ${s.cut_internal_silence ? "checked" : ""}>Encurtar pausas</label><label><span class="field-label">Limite em dB</span><input class="number-field setting-input" data-setting="silence_threshold_db" type="number" value="${s.silence_threshold_db}"></label><label><span class="field-label">Pausa minima</span><input class="number-field setting-input" data-setting="min_silence_duration" type="number" min=".1" step=".05" value="${s.min_silence_duration}"></label><label><span class="field-label">Pausa preservada</span><input class="number-field setting-input" data-setting="keep_silence" type="number" min="0" step=".05" value="${s.keep_silence}"></label><label><span class="field-label">Musica abaixo da voz (dB)</span><input class="number-field setting-input" data-setting="background_music_offset_db" type="number" min="-40" max="-4" step="1" value="${s.background_music_offset_db ?? -18}"></label></div></section>
    <section class="settings-group"><h3>Legenda</h3><div class="field-grid three"><label><span class="field-label">Estilo</span><select class="compact-select setting-input" data-setting="subtitle_mode"><option value="highlight" ${s.subtitle_mode === "highlight" ? "selected" : ""}>Palavra em destaque</option><option value="normal" ${s.subtitle_mode === "normal" ? "selected" : ""}>Legenda normal</option></select></label><label><span class="field-label">Fonte</span><select class="compact-select setting-input" data-setting="subtitle_font_name">${textFontOptions(s.subtitle_font_name || "Uninsta Heavy")}</select></label><label><span class="field-label">Palavras por linha</span><input class="number-field setting-input" data-setting="subtitle_words_per_line" type="number" min="1" max="6" value="${s.subtitle_words_per_line}"></label>${colorControl("subtitle_highlight_color", "Cor da palavra destacada", s.subtitle_highlight_color || "#FFEF00")}<label class="toggle-row"><input class="setting-input" data-setting="subtitle_force_caps" type="checkbox" ${s.subtitle_force_caps ? "checked" : ""}>Caixa alta</label><label class="toggle-row"><input class="setting-input" data-setting="subtitle_outline_enabled" type="checkbox" ${s.subtitle_outline_enabled ? "checked" : ""}>Contorno preto</label><label><span class="field-label">Espessura do contorno</span><input class="number-field setting-input" data-setting="subtitle_outline_size" type="number" min="0" max="12" step="1" value="${s.subtitle_outline_size ?? 3}"></label></div></section>
    <section class="settings-group headline-settings"><h3>Headline</h3><div class="field-grid three"><label class="toggle-row wide-field"><input class="setting-input" data-setting="headline_enabled" type="checkbox" ${s.headline_enabled ? "checked" : ""}>Exibir headline no inicio do video</label><label class="wide-field"><span class="field-label">Texto da headline</span><textarea class="text-field headline-text" id="headlineText" rows="4" placeholder="Escreva a headline. Cada quebra de linha sera mantida no video.">${escapeHtml(s.headline_text || "")}</textarea></label><label><span class="field-label">Duracao (segundos)</span><input class="number-field setting-input" data-setting="headline_duration" type="number" min=".1" step=".1" value="${s.headline_duration}"></label><label><span class="field-label">Fonte no video</span><input class="number-field setting-input" data-setting="headline_font_size" type="number" min="14" max="160" value="${s.headline_font_size}"></label><label><span class="field-label">Fonte</span><select class="compact-select setting-input" data-setting="headline_font_name">${textFontOptions(s.headline_font_name || "Uninsta Heavy")}</select></label><label><span class="field-label">Cor do texto</span><input class="color-field setting-input" data-setting="headline_text_color" type="color" value="${escapeHtml(s.headline_text_color || "#FFFFFF")}"></label><label class="toggle-row"><input class="setting-input" data-setting="headline_outline_enabled" type="checkbox" ${s.headline_outline_enabled ? "checked" : ""}>Contorno preto</label><label><span class="field-label">Espessura do contorno</span><input class="number-field setting-input" data-setting="headline_outline_size" type="number" min="0" max="12" step="1" value="${s.headline_outline_size ?? 0}"></label><label><span class="field-label">X (%)</span><input class="number-field setting-input" data-percent="true" data-setting="headline_x_position" type="number" min="0" max="100" step="1" value="${Math.round(Number(s.headline_x_position || .5) * 100)}"></label><label><span class="field-label">Y (%)</span><input class="number-field setting-input" data-percent="true" data-setting="headline_y_position" type="number" min="0" max="100" step="1" value="${Math.round(Number(s.headline_y_position || .2) * 100)}"></label><label><span class="field-label">Cor do fundo</span><input class="color-field setting-input" data-setting="headline_background_color" type="color" value="${escapeHtml(s.headline_background_color || "#12180F")}"></label><label><span class="field-label">Largura do fundo</span><input class="number-field setting-input" data-setting="headline_background_width" type="number" min="20" max="720" value="${s.headline_background_width}"></label><label><span class="field-label">Altura do fundo</span><input class="number-field setting-input" data-setting="headline_background_height" type="number" min="20" max="1280" value="${s.headline_background_height}"></label><label><span class="field-label">Cantos arredondados</span><input class="number-field setting-input" data-setting="headline_corner_radius" type="number" min="0" max="180" value="${s.headline_corner_radius}"></label></div></section>
    <section class="settings-group"><div class="settings-heading"><div><h3>Fontes locais</h3><p class="provider-note">${(state.available_fonts || []).length} fonte${(state.available_fonts || []).length === 1 ? "" : "s"} instalada${(state.available_fonts || []).length === 1 ? "" : "s"} no Creative Hub.</p></div><button class="secondary-button" id="importLocalFont" type="button"><i data-lucide="type"></i>Adicionar fonte</button></div></section>
  </div><aside class="preview-panel"><h3>Previa do criativo</h3><p>O tamanho e a posicao seguem a tela final de 720 x 1280. Arraste a legenda ou headline; ao chegar ao centro, as guias ajudam a alinhar.</p><label class="safe-zone-toggle"><input class="setting-input" data-setting="safe_zone_visible" type="checkbox" ${s.safe_zone_visible ? "checked" : ""}><span class="safe-zone-switch" aria-hidden="true"></span>Mostrar Safe Zone</label><div class="preview-stage" id="previewStage"><div class="preview-person"></div><div class="safe-zone" id="safeZone" aria-hidden="true"></div><div class="headline-guides" id="headlineGuides" aria-hidden="true"><i class="preview-guide vertical" id="verticalCenterGuide"></i><i class="preview-guide horizontal" id="horizontalCenterGuide"></i></div><img class="headline-render-preview" id="headlineRenderPreview" alt=""><div class="headline-preview" id="headlinePreview"><span id="headlinePreviewText"></span><i class="headline-resize-handle width" id="headlineWidthResizeHandle"></i><i class="headline-resize-handle height" id="headlineHeightResizeHandle"></i><i class="headline-resize-handle corner" id="headlineCornerResizeHandle"></i></div><div class="subtitle-preview" id="creativeSubtitlePreview"><span>${captionPreviewText(s)}</span><i class="resize-handle" id="subtitleResizeHandle"></i></div></div><div class="preview-values"><div class="preview-value"><small>X</small><strong id="previewX">--</strong></div><div class="preview-value"><small>Y</small><strong id="previewY">--</strong></div><div class="preview-value"><small>Fonte no video</small><strong id="previewSize">--</strong></div></div></aside></div>`;
  bindSettingsInputs();
  $("#goToIntegrations")?.addEventListener("click", goToIntegrations);
  bindSubtitlePreview();
  bindHeadlinePreview();
  bindHeadlineText();
  $("#importLocalFont")?.addEventListener("click", importLocalFont);
  syncPreview();
}

function renderIntegrationsView() {
  const s = state.settings;
  const provider = s.voice_provider || "clone";
  const voiceSpeed = Number(s.voice_speed ?? 1).toFixed(2);
  const assemblyStatus = s.assemblyai_api_configured ? "Chave salva localmente e pronta para uso." : "Nenhuma chave configurada.";
  const voiceLibrary = `<label><span class="field-label">Biblioteca</span><select class="compact-select" id="voiceProvider"><option value="clone" ${provider === "clone" ? "selected" : ""}>Minhas vozes clonadas</option><option value="elevenlabs" ${provider === "elevenlabs" ? "selected" : ""}>ElevenLabs</option><option value="minimax" ${provider === "minimax" ? "selected" : ""}>Minimax</option><option value="edge" ${provider === "edge" ? "selected" : ""}>Microsoft Edge</option><option value="kokoro" ${provider === "kokoro" ? "selected" : ""}>Kokoro</option><option value="vbee" ${provider === "vbee" ? "selected" : ""}>Vbee</option><option value="fishaudio" ${provider === "fishaudio" ? "selected" : ""}>Fish Audio</option></select></label>`;
  const voiceSettings = `<section class="settings-group"><div class="settings-heading"><div><h3>Geracao de voz</h3><p class="provider-note">A OpenSpeaker gera as narracoes das copies usando as vozes da sua conta.</p></div><span class="connection-status" id="voiceConnection">${escapeHtml(voiceConnection)}</span></div><div class="field-grid"><label class="wide-field"><span class="field-label">Chave da API OpenSpeaker</span><div class="api-key-row"><input class="text-field" id="voiceApiKey" type="password" value="" placeholder="Chave salva localmente; nao sera exibida novamente"><button class="secondary-button" id="loadVoices" type="button"><i data-lucide="plug-zap"></i>Carregar vozes</button></div></label>${voiceLibrary}<label><span class="field-label">Voz padrao</span><select class="compact-select" id="defaultVoice">${voiceOptions(s.voice_name)}</select></label><label><span class="field-label">Velocidade da narracao</span><input class="number-field" id="voiceSpeed" type="number" min="0.5" max="1.5" step="0.01" value="${voiceSpeed}"></label></div></section>`;
  const transcriptionSettings = `<section class="settings-group"><div class="settings-heading"><div><h3>AssemblyAI</h3><p class="provider-note">Usada opcionalmente para transcrever o audio dos criativos.</p></div><span class="connection-status ${s.assemblyai_api_configured ? "connected" : ""}">${escapeHtml(assemblyStatus)}</span></div><div class="field-grid"><label class="wide-field"><span class="field-label">Chave da API AssemblyAI</span><input class="text-field" id="assemblyApiKey" type="password" value="" placeholder="Chave salva localmente; nao sera exibida novamente"></label><label><span class="field-label">Modelo</span><input class="text-field" value="Universal-3.5 Pro" disabled></label></div></section>`;
  $("#integrationsView").innerHTML = `<div class="settings-layout">${voiceSettings}${transcriptionSettings}</div>`;
  $("#loadVoices").addEventListener("click", loadVoices);
  $("#voiceProvider").addEventListener("change", event => { state.settings.voice_provider = event.target.value; loadVoices(); });
  $("#defaultVoice").addEventListener("change", event => { state.settings.voice_name = event.target.value; scheduleSettingsSave(); renderCreativeView(); refreshIcons(); });
  $("#assemblyApiKey").addEventListener("change", event => { state.settings.assemblyai_api_key = event.target.value; scheduleSettingsSave(); });
  $("#voiceSpeed").addEventListener("change", event => { if (!event.target.validity.valid) { event.target.value = voiceSpeed; showError(new Error("Use uma velocidade entre 0,50 e 1,50.")); return; } state.settings.voice_speed = Number(event.target.value); scheduleSettingsSave(); });
}

function renderPerformanceView() {
  const concurrency = Number(state.settings.render_concurrency) === 1 ? 1 : 2;
  $("#performanceView").innerHTML = `<div class="settings-layout"><section class="settings-group"><h3>Renderizacao de video</h3><p class="provider-note">Escolha quantos videos o Creative Hub renderiza ao mesmo tempo. Use 1 em computadores com menos folga; 2 e o modo rapido padrao.</p><div class="field-grid"><label><span class="field-label">Renderizacoes simultaneas</span><select class="compact-select setting-input" data-setting="render_concurrency"><option value="1" ${concurrency === 1 ? "selected" : ""}>1 - Modo economico</option><option value="2" ${concurrency === 2 ? "selected" : ""}>2 - Modo rapido</option></select></label></div></section></div>`;
  bindSettingsInputs();
}

function renderSettingsView() {
  const s = state.settings;
  const provider = s.voice_provider || "clone";
  const transcriptionProvider = s.transcription_provider || "local";
  const assemblyStatus = s.assemblyai_api_configured ? "Chave salva localmente." : "Informe a chave para usar a API.";
  $("#settingsView").innerHTML = `<div class="settings-layout"><section class="settings-group"><div class="settings-heading"><div><h3>Geracao de voz</h3><p class="provider-note">Sua chave fica apenas nesta maquina. Conecte para carregar as vozes que pertencem a sua conta.</p></div><span class="connection-status" id="voiceConnection">${escapeHtml(voiceConnection)}</span></div><div class="field-grid"><label class="wide-field"><span class="field-label">Chave da API OpenSpeaker</span><div class="api-key-row"><input class="text-field" id="voiceApiKey" type="password" value="" placeholder="Chave salva localmente; nao sera exibida novamente"><button class="secondary-button" id="loadVoices" type="button"><i data-lucide="plug-zap"></i>Carregar vozes</button></div></label><label><span class="field-label">Biblioteca</span><select class="compact-select" id="voiceProvider"><option value="clone" ${provider === "clone" ? "selected" : ""}>Minhas vozes clonadas</option><option value="elevenlabs" ${provider === "elevenlabs" ? "selected" : ""}>ElevenLabs</option><option value="minimax" ${provider === "minimax" ? "selected" : ""}>Minimax</option><option value="edge" ${provider === "edge" ? "selected" : ""}>Microsoft Edge</option><option value="kokoro" ${provider === "kokoro" ? "selected" : ""}>Kokoro</option><option value="vbee" ${provider === "vbee" ? "selected" : ""}>Vbee</option><option value="fishaudio" ${provider === "fishaudio" ? "selected" : ""}>Fish Audio</option></select></label><label><span class="field-label">Voz padrao</span><select class="compact-select" id="defaultVoice">${voiceOptions(s.voice_name)}</select></label></div></section><section class="settings-group"><div class="settings-heading"><div><h3>Transcricao</h3><p class="provider-note">O modo local usa o Whisper no seu computador. A API usa o Universal-3.5 Pro da AssemblyAI.</p></div><span class="connection-status">${escapeHtml(assemblyStatus)}</span></div><div class="field-grid"><label><span class="field-label">Provedor</span><select class="compact-select setting-input" data-setting="transcription_provider"><option value="local" ${transcriptionProvider === "local" ? "selected" : ""}>Whisper local</option><option value="assemblyai" ${transcriptionProvider === "assemblyai" ? "selected" : ""}>AssemblyAI</option></select></label>${transcriptionProvider === "assemblyai" ? `<label class="wide-field"><span class="field-label">Chave da API AssemblyAI</span><input class="text-field" id="assemblyApiKey" type="password" value="" placeholder="Chave salva localmente; nao sera exibida novamente"></label>` : ""}<label><span class="field-label">Modelo</span><input class="text-field" value="Universal-3.5 Pro" disabled></label></div></section><section class="settings-group"><h3>Audio manual</h3><p>Use esta pasta como referencia para manter seus arquivos de narracao organizados. Os cards continuam aceitando um audio individual quando necessario.</p>${folderInput("manual_audio_folder", "Pasta de audios", s.manual_audio_folder)}</section></div>`;
  bindSettingsInputs();
  $("#loadVoices").addEventListener("click", loadVoices);
  $("#voiceProvider").addEventListener("change", event => { state.settings.voice_provider = event.target.value; loadVoices(); });
  $("#defaultVoice").addEventListener("change", event => { state.settings.voice_name = event.target.value; scheduleSettingsSave(); renderCreativeView(); refreshIcons(); });
  $("#assemblyApiKey")?.addEventListener("change", event => { state.settings.assemblyai_api_key = event.target.value; scheduleSettingsSave(); });
}

function folderInput(setting, label, value) {
  return `<label><span class="field-label">${label}</span><div class="folder-field"><input class="text-field setting-input" data-setting="${setting}" value="${escapeHtml(value || "")}" placeholder="Selecione uma pasta"><button class="icon-button select-folder" data-setting="${setting}" type="button" aria-label="Escolher pasta" title="Escolher pasta"><i data-lucide="folder-open"></i></button></div></label>`;
}

function fileInput(setting, label, value) {
  return `<label><span class="field-label">${label}</span><div class="folder-field"><input class="text-field setting-input" data-setting="${setting}" value="${escapeHtml(value || "")}" placeholder="Selecione um video"><button class="icon-button select-file" data-setting="${setting}" type="button" aria-label="Escolher video" title="Escolher video"><i data-lucide="film"></i></button></div></label>`;
}

function offerFolderInput(field, label, value) {
  return `<label><span class="field-label">${label}</span><div class="folder-field offer-folder-field"><input class="text-field offer-input" data-offer-field="${field}" value="${escapeHtml(value || "")}" placeholder="Selecione uma pasta"><button class="icon-button select-offer-folder" data-offer-field="${field}" type="button" aria-label="Escolher pasta" title="Escolher pasta"><i data-lucide="folder-open"></i></button><button class="icon-button open-offer-folder" data-offer-field="${field}" type="button" aria-label="Abrir no Explorador" title="Abrir no Explorador"><i data-lucide="external-link"></i></button></div></label>`;
}

function offerFileInput(field, label, value) {
  return `<label><span class="field-label">${label}</span><div class="folder-field offer-folder-field"><input class="text-field offer-input" data-offer-field="${field}" value="${escapeHtml(value || "")}" placeholder="Selecione um video"><button class="icon-button select-offer-file" data-offer-field="${field}" type="button" aria-label="Escolher video" title="Escolher video"><i data-lucide="film"></i></button><button class="icon-button open-offer-folder" data-offer-field="${field}" type="button" aria-label="Abrir pasta do B-roll no Explorador" title="Abrir no Explorador"><i data-lucide="external-link"></i></button></div></label>`;
}

function bindOfferInputs(target, offerId) {
  bindSettingsInputs();
  $$(".offer-input", target).forEach(input => input.addEventListener("change", event => updateOffer(offerId, { [event.target.dataset.offerField]: event.target.value })));
  $$("[data-offer-music-mode]", target).forEach(button => button.addEventListener("click", () => updateOffer(offerId, { background_music_mode: button.dataset.offerMusicMode })));
  $$(".music-preview-track", target).forEach(button => button.addEventListener("click", () => previewBackgroundMusic(button.dataset.musicPreview, button)));
  $$(".select-offer-folder", target).forEach(button => button.addEventListener("click", () => selectOfferPath("/api/select-folder", offerId, button.dataset.offerField, button)));
  $$(".select-offer-file", target).forEach(button => button.addEventListener("click", () => selectOfferPath("/api/select-file", offerId, button.dataset.offerField, button)));
  $$(".open-offer-folder", target).forEach(button => button.addEventListener("click", () => openOfferFolder(offerId, button.dataset.offerField)));
}

function bindSettingsInputs() {
  $$(".setting-input").forEach(input => input.addEventListener("change", event => {
    const value = inputValue(event.target);
    state.settings[event.target.dataset.setting] = value;
    if (event.target.type === "color") {
      const hexInput = event.target.closest(".color-control")?.querySelector(".hex-input");
      if (hexInput) hexInput.value = value.slice(1).toUpperCase();
    }
    scheduleSettingsSave();
    syncPreview();
  }));
  $$(".hex-toggle").forEach(button => { button.onclick = toggleHex; });
  $$(".hex-input").forEach(input => input.addEventListener("input", event => { const normalized = colorUtils.normalizeHexColor(event.target.value); const control = event.target.closest(".color-control"); control.classList.toggle("invalid", !normalized && Boolean(event.target.value)); if (!normalized) return; state.settings[event.target.dataset.setting] = normalized; control.querySelector("input[type=color]").value = normalized; syncPreview(); scheduleSettingsSave(); }));
  $$(".select-folder").forEach(button => button.addEventListener("click", () => selectFolder(button.dataset.setting, button)));
  $$(".select-file").forEach(button => button.addEventListener("click", () => selectFile(button.dataset.setting, button)));
}

function toggleHex(event) {
  const button = event.currentTarget;
  const control = button.closest(".color-control");
  const open = !control.classList.contains("hex-open");
  control.classList.toggle("hex-open", open);
  button.setAttribute("aria-expanded", String(open));
}

function inputValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return input.dataset.percent === "true" ? Number(input.value) / 100 : Number(input.value);
  return input.value;
}

function bindSubtitlePreview() {
  const preview = $("#creativeSubtitlePreview");
  const stage = $("#previewStage");
  const handle = $("#subtitleResizeHandle");
  preview.addEventListener("pointerdown", event => {
    if (event.target === handle) return;
    beginSubtitleInteraction(event, preview, { mode: "move", kind: "subtitle", pointerId: event.pointerId, stage });
  });
  handle.addEventListener("pointerdown", event => {
    event.stopPropagation();
    beginSubtitleInteraction(event, handle, { mode: "resize", kind: "subtitle", pointerId: event.pointerId, stage, startY: event.clientY, startSize: Number(state.settings.subtitle_font_size) });
  });
}

function bindHeadlinePreview() {
  const preview = $("#headlinePreview");
  const stage = $("#previewStage");
  const widthHandle = $("#headlineWidthResizeHandle");
  const heightHandle = $("#headlineHeightResizeHandle");
  const cornerHandle = $("#headlineCornerResizeHandle");
  preview.addEventListener("pointerdown", event => {
    if (event.target.classList.contains("headline-resize-handle")) return;
    beginSubtitleInteraction(event, preview, { mode: "move", kind: "headline", pointerId: event.pointerId, stage });
  });
  bindHeadlineResizeHandle(widthHandle, "resize-width", stage);
  bindHeadlineResizeHandle(heightHandle, "resize-height", stage);
  bindHeadlineResizeHandle(cornerHandle, "resize-both", stage);
}

function bindHeadlineResizeHandle(handle, mode, stage) {
  handle.addEventListener("pointerdown", event => {
    event.stopPropagation();
    beginSubtitleInteraction(event, handle, {
      mode,
      kind: "headline",
      pointerId: event.pointerId,
      stage,
      startX: event.clientX,
      startY: event.clientY,
      startWidth: Number(state.settings.headline_background_width),
      startHeight: Number(state.settings.headline_background_height),
      startHeadlineX: numberSetting(state.settings.headline_x_position, .5),
      startHeadlineY: numberSetting(state.settings.headline_y_position, .2),
    });
  });
}

function bindHeadlineText() {
  $("#headlineText")?.addEventListener("input", event => {
    state.settings.headline_text = event.target.value;
    syncPreview();
    scheduleSettingsSave();
  });
}

function beginSubtitleInteraction(event, target, nextState) {
  dragState = nextState;
  target.setPointerCapture(event.pointerId);
  window.addEventListener("pointermove", moveSubtitlePreview);
  window.addEventListener("pointerup", endSubtitlePreview, { once: true });
}

function moveSubtitlePreview(event) {
  if (!dragState) return;
  const rect = dragState.stage.getBoundingClientRect();
  if (dragState.mode === "move") {
    const x = snapToCenter(clamp((event.clientX - rect.left) / rect.width, 0, 1));
    const y = snapToCenter(clamp((event.clientY - rect.top) / rect.height, 0, 1));
    const prefix = dragState.kind === "headline" ? "headline" : "subtitle";
    state.settings[`${prefix}_x_position`] = x.value;
    state.settings[`${prefix}_y_position`] = y.value;
    setCenterGuides(x.snapped, y.snapped);
  } else if (dragState.kind === "headline") {
    resizeHeadlinePreview(event, rect);
  } else {
    const scale = previewMetrics.captionMetrics(rect.width, 1).scale || 1;
    state.settings.subtitle_font_size = clamp(Math.round(dragState.startSize + (event.clientY - dragState.startY) / scale), 14, 120);
  }
  syncPreview();
}

function endSubtitlePreview() {
  if (!dragState) return;
  dragState = null;
  window.removeEventListener("pointermove", moveSubtitlePreview);
  setCenterGuides(false, false);
  scheduleSettingsSave();
}

function resizeHeadlinePreview(event, rect) {
  const scale = previewMetrics.captionMetrics(rect.width, 1).scale || 1;
  const resizeWidth = dragState.mode === "resize-width" || dragState.mode === "resize-both";
  const resizeHeight = dragState.mode === "resize-height" || dragState.mode === "resize-both";
  if (resizeWidth) {
    const startLeft = dragState.startHeadlineX * 720 - dragState.startWidth / 2;
    const width = clamp(Math.round(dragState.startWidth + (event.clientX - dragState.startX) / scale), 40, Math.max(40, 720 - startLeft));
    state.settings.headline_background_width = width;
    state.settings.headline_x_position = clamp((startLeft + width / 2) / 720, 0, 1);
  }
  if (resizeHeight) {
    const startTop = dragState.startHeadlineY * 1280 - dragState.startHeight / 2;
    const height = clamp(Math.round(dragState.startHeight + (event.clientY - dragState.startY) / scale), 40, Math.max(40, 1280 - startTop));
    state.settings.headline_background_height = height;
    state.settings.headline_y_position = clamp((startTop + height / 2) / 1280, 0, 1);
  }
}

function snapToCenter(value) {
  const snapped = Math.abs(value - .5) <= .018;
  return { value: snapped ? .5 : value, snapped };
}

function setCenterGuides(showVertical, showHorizontal) {
  $("#verticalCenterGuide")?.classList.toggle("visible", showVertical);
  $("#horizontalCenterGuide")?.classList.toggle("visible", showHorizontal);
}

function syncPreview() {
  const preview = $("#creativeSubtitlePreview");
  const stage = $("#previewStage");
  if (!preview) return;
  const s = state.settings;
  $("#safeZone")?.classList.toggle("visible", Boolean(s.safe_zone_visible));
  const subtitleOutline = s.subtitle_outline_enabled ? Number(s.subtitle_outline_size ?? 3) : 0;
  const metrics = previewMetrics.captionMetrics(previewMetrics.visibleStageWidth(stage.clientWidth), Number(s.subtitle_font_size || 24), subtitleOutline);
  Object.assign(preview.style, previewMetrics.captionLayout());
  preview.style.left = `${numberSetting(s.subtitle_x_position, .5) * 100}%`;
  preview.style.top = `${numberSetting(s.subtitle_y_position, .66) * 100}%`;
  preview.style.fontSize = `${metrics.fontSize}px`;
  preview.style.fontFamily = `"${s.subtitle_font_name || "Uninsta Heavy"}", Arial, sans-serif`;
  preview.style.setProperty("--caption-highlight", s.subtitle_highlight_color || "#FFEF00");
  preview.classList.toggle("no-outline", subtitleOutline <= 0);
  preview.style.setProperty("--caption-outline", `${metrics.outline}px`);
  preview.querySelector("span").innerHTML = captionPreviewText(s);
  const headline = $("#headlinePreview");
  if (headline) {
    const scale = metrics.scale || 1;
    const visible = Boolean(s.headline_enabled && String(s.headline_text || "").trim());
    headline.classList.toggle("visible", visible);
    headline.style.left = `${numberSetting(s.headline_x_position, .5) * 100}%`;
    headline.style.top = `${numberSetting(s.headline_y_position, .2) * 100}%`;
    headline.style.width = `${Number(s.headline_background_width || 560) * scale}px`;
    headline.style.height = `${Number(s.headline_background_height || 150) * scale}px`;
    headline.style.borderRadius = `${Number(s.headline_corner_radius || 0) * scale}px`;
    headline.style.backgroundColor = s.headline_background_color || "#12180F";
    headline.style.color = s.headline_text_color || "#FFFFFF";
    headline.style.fontSize = `${Number(s.headline_font_size || 48) * scale}px`;
    headline.style.fontFamily = `"${s.headline_font_name || "Uninsta Heavy"}", Arial, sans-serif`;
    headline.style.setProperty("--headline-outline", `${(s.headline_outline_enabled ? Number(s.headline_outline_size ?? 0) : 0) * scale}px`);
    headline.classList.toggle("no-outline", !s.headline_outline_enabled || Number(s.headline_outline_size ?? 0) <= 0);
    $("#headlinePreviewText").textContent = s.headline_text || "";
    scheduleHeadlineRender(s, visible);
  }
  $("#previewX").textContent = Math.round(Number(s.subtitle_x_position || .5) * 100) + "%";
  $("#previewY").textContent = Math.round(Number(s.subtitle_y_position || .66) * 100) + "%";
  $("#previewSize").textContent = `${s.subtitle_font_size || 24}px`;
}

function scheduleHeadlineRender(settings, visible) {
  clearTimeout(headlineRenderTimer);
  const image = $("#headlineRenderPreview");
  const fallback = $("#headlinePreview");
  if (!image || !fallback) return;
  const requestId = ++headlinePreviewRequest;
  if (!visible) {
    image.classList.remove("visible");
    fallback.classList.remove("render-ready");
    return;
  }
  const payload = Object.fromEntries(Object.entries(settings).filter(([key]) => key.startsWith("headline_")));
  headlineRenderTimer = setTimeout(() => loadHeadlineRender(payload, requestId), 180);
}

async function loadHeadlineRender(payload, requestId) {
  try {
    const response = await fetch("/api/headline-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok || requestId !== headlinePreviewRequest) return;
    const image = $("#headlineRenderPreview");
    const fallback = $("#headlinePreview");
    if (!image || !fallback) return;
    const oldUrl = headlinePreviewUrl;
    const newUrl = URL.createObjectURL(await response.blob());
    const stagedImage = new Image();
    stagedImage.onload = () => {
      if (requestId !== headlinePreviewRequest) {
        URL.revokeObjectURL(newUrl);
        return;
      }
      headlinePreviewUrl = newUrl;
      image.src = newUrl;
      image.classList.add("visible");
      fallback.classList.add("render-ready");
      if (oldUrl) URL.revokeObjectURL(oldUrl);
    };
    stagedImage.src = newUrl;
  } catch (_) {
    // The CSS fallback keeps the editor usable if the local preview renderer is unavailable.
  }
}

async function createCopy() { try { const result = await api("/api/copies", "POST", { title: "", text: "" }); syncOfferCopy(result.copy); render(); showToast("Copy criada."); } catch (error) { showError(error); } }
function createOffer() { openCreateOfferModal(); }
async function activateOffer(id) { try { await api(`/api/offers/${encodeURIComponent(id)}/activate`, "POST", {}); await loadState(); } catch (error) { showError(error); } }
async function updateOffer(id, patch) { try { await api(`/api/offers/${encodeURIComponent(id)}`, "PUT", patch); await loadState(); showSaved(); } catch (error) { showError(error); } }
async function selectOfferPath(route, offerId, field, button) { if (pickerOpen) return; pickerOpen = true; button.disabled = true; try { const result = await api(route, "POST", { current_path: state.active_offer?.[field] || "" }); if (!result.cancelled) await updateOffer(offerId, { [field]: result.path }); } catch (error) { showError(error); } finally { pickerOpen = false; button.disabled = false; } }
async function openOfferFolder(offerId, field) { try { await api(`/api/offers/${encodeURIComponent(offerId)}/open-folder`, "POST", { field }); } catch (error) { showError(error); } }
function openCreateOfferModal() { openOfferModal("create"); }
function openDeleteOfferModal(offer) { openOfferModal("delete", offer); }
function openOfferModal(mode, offer = null) {
  offerModalMode = { mode, offer };
  const modal = $("#offerModal");
  const isDelete = mode === "delete";
  $("#offerModalKicker").textContent = isDelete ? "EXCLUIR OFERTA" : "NOVA OFERTA";
  $("#offerModalTitle").textContent = isDelete ? `Excluir ${offer.name}?` : "Criar nova oferta";
  $("#offerModalDescription").textContent = isDelete ? `A pasta ${offer.slug} dentro da central de ofertas sera removida. Arquivos em caminhos externos nao serao apagados.` : "Crie uma area isolada para takes, B-roll, audios, outputs e transcricoes.";
  $("#offerNameField").hidden = isDelete;
  $("#offerNameInput").value = "";
  $("#offerModalConfirm").textContent = isDelete ? "Excluir oferta" : "Criar oferta";
  $("#offerModalConfirm").classList.toggle("danger-button", isDelete);
  modal.hidden = false;
  requestAnimationFrame(() => (isDelete ? $("#offerModalConfirm") : $("#offerNameInput")).focus());
}
function closeOfferModal() { $("#offerModal").hidden = true; offerModalMode = null; }
async function confirmOfferModal() {
  const action = offerModalMode;
  if (!action) return;
  try {
    if (action.mode === "create") {
      const name = $("#offerNameInput").value.trim();
      if (!name) return showError(new Error("Informe o nome da oferta."));
      await api("/api/offers", "POST", { name });
      selectedIds.clear();
      showToast("Oferta criada.");
    } else {
      await api(`/api/offers/${encodeURIComponent(action.offer.id)}`, "DELETE");
      selectedIds.clear();
      showToast("Oferta removida.");
    }
    closeOfferModal();
    await loadState();
  } catch (error) { showError(error); }
}
function goToIntegrations() { showView("integrations"); }
function scheduleCopyUpdate(id, patch) { const pending = { ...(pendingCopyPatches.get(id) || {}), ...patch }; pendingCopyPatches.set(id, pending); clearTimeout(copyTimers.get(id)); showSaved("Salvando..."); copyTimers.set(id, setTimeout(() => { pendingCopyPatches.delete(id); updateCopy(id, pending); }, 350)); }
async function updateCopy(id, patch, rerender = false) { try { const result = await api(`/api/copies/${id}`, "PUT", patch); replaceCopy(result.copy, rerender); showSaved(); } catch (error) { showError(error); } }
async function duplicateCopy(id) { try { const result = await api(`/api/copies/${id}/duplicate`, "POST", {}); syncOfferCopy(result.copy); render(); showToast("Copy duplicada."); } catch (error) { showError(error); } }
async function deleteCopy(id) { try { await api(`/api/copies/${id}`, "DELETE"); selectedIds.delete(id); removeOfferCopy(id); render(); showToast("Copy removida."); } catch (error) { showError(error); } }
async function attachAudio(id, audioPath) { try { const result = await api(`/api/copies/${id}/audio`, "POST", { audio_path: audioPath }); replaceCopy(result.copy); render(); showToast("Audio vinculado."); } catch (error) { showError(error); } }
function syncOfferCopy(updated) {
  const exists = state.copies.some(copy => copy.id === updated.id);
  state.copies = exists ? state.copies.map(copy => copy.id === updated.id ? updated : copy) : [...state.copies, updated];
  syncActiveOfferCopies();
}
function removeOfferCopy(id) {
  state.copies = state.copies.filter(copy => copy.id !== id);
  syncActiveOfferCopies();
}
function syncActiveOfferCopies() {
  const copies = state.copies || [];
  state.offers = (state.offers || []).map(offer => offer.id === state.active_offer_id ? { ...offer, copies } : offer);
  if (state.active_offer?.id === state.active_offer_id) state.active_offer = { ...state.active_offer, copies };
}
function replaceCopy(updated, rerender = true) { syncOfferCopy(updated); if (rerender) { renderCreativeView(); refreshIcons(); } }

async function selectFolder(setting, button) { await selectLocalPath("/api/select-folder", setting, button); }
async function selectFile(setting, button) { await selectLocalPath("/api/select-file", setting, button); }
async function importLocalFont() {
  if (pickerOpen) return;
  pickerOpen = true;
  try {
    const selected = await api("/api/select-font", "POST", { current_path: "" });
    if (selected.cancelled) return;
    const result = await api("/api/fonts/import", "POST", { font_path: selected.path });
    state.available_fonts = result.available_fonts || [];
    render();
    showToast("Fonte adicionada ao Creative Hub.");
  } catch (error) { showError(error); } finally { pickerOpen = false; }
}
async function selectLocalPath(route, setting, button) { if (pickerOpen) return; pickerOpen = true; if (button) button.disabled = true; try { const result = await api(route, "POST", { current_path: state.settings[setting] || "" }); if (!result.cancelled) { state.settings[setting] = result.path; render(); scheduleSettingsSave(); } } catch (error) { showError(error); } finally { pickerOpen = false; if (button) button.disabled = false; } }
function scheduleSettingsSave() { clearTimeout(saveTimer); showSaved("Salvando..."); saveTimer = setTimeout(saveSettings, 350); }
async function saveSettings() { try { const result = await api("/api/settings", "PUT", state.settings); const { voice_api_key, assemblyai_api_key, ...publicSettings } = result.settings; state.settings = { ...state.settings, ...publicSettings }; showSaved(); } catch (error) { showError(error); } }

async function loadVoices({ automatic = false } = {}) {
  const keyInput = $("#voiceApiKey");
  if (keyInput?.value) state.settings.voice_api_key = keyInput.value;
  const provider = $("#voiceProvider")?.value || state.settings.voice_provider || "clone";
  state.settings.voice_provider = provider;
  voiceConnection = automatic ? "Restaurando vozes salvas..." : "Verificando chave e carregando vozes...";
  renderIntegrationsView();
  refreshIcons();
  try {
    await saveSettings();
    const result = await api(`/api/voices?provider=${encodeURIComponent(provider)}`);
    voiceLibrary = result.voices;
    if (voiceLibrary.length && !voiceLibrary.some(voice => voice.id === state.settings.voice_name)) {
      state.settings.voice_name = voiceLibrary[0].id;
      await saveSettings();
    }
    voiceConnection = voiceLibrary.length ? `${voiceLibrary.length} voz${voiceLibrary.length === 1 ? "" : "es"} disponivel${voiceLibrary.length === 1 ? "" : "is"}.` : "Chave valida. Nenhuma voz encontrada nesta biblioteca.";
    renderIntegrationsView();
    renderCreativeView();
    refreshIcons();
  } catch (error) {
    voiceLibrary = [];
    voiceConnection = error.message || "Nao foi possivel conectar.";
    renderIntegrationsView();
    refreshIcons();
  }
}

async function startRender(testOnly) { const copyIds = [...selectedIds]; if (!copyIds.length) return showError(new Error("Selecione pelo menos um criativo.")); try { await api(testOnly ? "/api/render/test" : "/api/render/batch", "POST", { copy_ids: copyIds }); showToast(testOnly ? "Teste iniciado." : "Lote iniciado."); watchJob(); } catch (error) { showError(error); } }
async function startVoiceGeneration() { const copyIds = [...selectedIds]; if (!copyIds.length) return showError(new Error("Selecione pelo menos um criativo.")); try { await api("/api/voice/generate", "POST", { copy_ids: copyIds }); showToast("Geracao de audio iniciada."); watchJob(); } catch (error) { showError(error); } }
function toggleAllCopies() { const allSelected = state.copies.length > 0 && state.copies.every(copy => selectedIds.has(copy.id)); state.copies.forEach(copy => allSelected ? selectedIds.delete(copy.id) : selectedIds.add(copy.id)); renderCreativeView(); refreshIcons(); }
async function importManualAudio() {
  const offer = state.active_offer;
  if (!offer?.manual_audio_inbox_folder) return showError(new Error("Configure a entrada de audios manuais desta oferta antes de importar."));
  try {
    const result = await api(`/api/offers/${encodeURIComponent(offer.id)}/manual-audio/import`, "POST", {});
    await loadState();
    if (result.empty) return showToast("Nao ha audios novos na entrada desta oferta.");
    const imported = Number(result.imported_count || 0);
    const skipped = Number(result.skipped_count || 0);
    const importedLabel = `${imported} audio${imported === 1 ? "" : "s"} importado${imported === 1 ? "" : "s"}`;
    showToast(skipped ? `${importedLabel}. ${skipped} arquivo${skipped === 1 ? "" : "s"} ignorado${skipped === 1 ? "" : "s"}.` : `${importedLabel}.`);
  } catch (error) { showError(error); }
}

function isBatchEligible(copy) {
  return Boolean(String(copy.text || "").trim()) || (
    copy.audio_source === "manual" && Boolean(String(copy.audio_path || "").trim())
  );
}

function offersForBatch(scope) {
  const offers = state.offers || [];
  if (scope === "active") return offers.filter(offer => offer.id === state.active_offer_id && (offer.copies || []).some(isBatchEligible));
  return offers.filter(offer => (offer.copies || []).some(isBatchEligible));
}

function ensureBatchSetupModal() {
  let modal = $("#batchSetupModal");
  if (modal) return modal;
  document.body.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="batchSetupModal" hidden><section class="app-modal batch-setup-modal" role="dialog" aria-modal="true" aria-labelledby="batchSetupTitle"><div class="modal-heading"><div><p class="section-kicker">PRODUCAO</p><h2 id="batchSetupTitle">Configurar lote</h2></div><button class="icon-button" id="batchSetupClose" type="button" aria-label="Fechar"><i data-lucide="x"></i></button></div><div class="batch-setup-body"><p class="modal-description" id="batchSetupDescription"></p><div class="batch-mode-options" role="radiogroup" aria-label="Modo de nomeacao do lote"><label><input type="radio" name="batchMode" value="automatic" checked><span><strong>Automatico</strong><small>O Hub cria o proximo lote de cada oferta.</small></span></label><label><input type="radio" name="batchMode" value="custom"><span><strong>Personalizado</strong><small>Defina um nome para cada oferta incluida.</small></span></label></div><div class="batch-custom-names" id="batchCustomNames" hidden></div></div><div class="modal-actions"><button class="secondary-button" id="batchSetupCancel" type="button">Cancelar</button><button class="primary-button" id="batchSetupConfirm" type="button"><i data-lucide="play"></i>Iniciar lote</button></div></section></div>`);
  modal = $("#batchSetupModal");
  $("#batchSetupClose", modal).addEventListener("click", closeBatchSetup);
  $("#batchSetupCancel", modal).addEventListener("click", closeBatchSetup);
  $("#batchSetupConfirm", modal).addEventListener("click", confirmBatchSetup);
  $$('input[name="batchMode"]', modal).forEach(input => input.addEventListener("change", syncBatchSetupMode));
  modal.addEventListener("click", event => { if (event.target === event.currentTarget) closeBatchSetup(); });
  return modal;
}

function openBatchSetup(scope) {
  const offers = offersForBatch(scope);
  if (!offers.length) return showError(new Error(scope === "active" ? "Adicione uma copy com texto ou audio manual vinculado nesta oferta antes de gerar." : "Adicione uma copy com texto ou audio manual vinculado antes de gerar o lote."));
  const modal = ensureBatchSetupModal();
  modal.dataset.scope = scope;
  $("#batchSetupTitle", modal).textContent = scope === "active" ? "Gerar esta oferta" : "Gerar todas as ofertas";
  $("#batchSetupDescription", modal).textContent = scope === "active" ? `O lote sera salvo no output de ${offers[0].name}.` : `${offers.length} ofertas participarao desta producao.`;
  $("#batchCustomNames", modal).innerHTML = offers.map(offer => `<label><span class="field-label">${escapeHtml(offer.name)}</span><input class="text-field batch-name-input" data-offer-id="${escapeHtml(offer.id)}" maxlength="80" placeholder="Nome do lote"></label>`).join("");
  $("input[value=automatic]", modal).checked = true;
  syncBatchSetupMode();
  modal.hidden = false;
  requestAnimationFrame(() => $("input[value=automatic]", modal).focus());
  refreshIcons();
}

function syncBatchSetupMode() {
  const modal = $("#batchSetupModal");
  if (!modal) return;
  const isCustom = $("input[name=batchMode]:checked", modal)?.value === "custom";
  $("#batchCustomNames", modal).hidden = !isCustom;
  if (isCustom) requestAnimationFrame(() => $(".batch-name-input", modal)?.focus());
}

function closeBatchSetup() {
  const modal = $("#batchSetupModal");
  if (modal) modal.hidden = true;
}

function ensureVideoPlayerModal() {
  let modal = $("#videoPlayerModal");
  if (modal) return modal;
  document.body.insertAdjacentHTML("beforeend", `<div class="modal-backdrop video-player-modal" id="videoPlayerModal" hidden><section class="app-modal video-player-dialog" role="dialog" aria-modal="true" aria-labelledby="videoPlayerTitle"><div class="video-player-heading"><h2 id="videoPlayerTitle">Video renderizado</h2><button class="icon-button" id="videoPlayerClose" type="button" aria-label="Fechar video" title="Fechar video"><i data-lucide="x"></i></button></div><video id="nativeVideoPlayer" controls playsinline></video></section></div>`);
  modal = $("#videoPlayerModal");
  $("#videoPlayerClose", modal).addEventListener("click", closeVideoPlayer);
  modal.addEventListener("click", event => { if (event.target === event.currentTarget) closeVideoPlayer(); });
  return modal;
}

function openVideoPlayer(videoPath) {
  if (!videoPath) return;
  const modal = ensureVideoPlayerModal();
  const video = $("#nativeVideoPlayer", modal);
  $("#videoPlayerTitle", modal).textContent = videoPath.split(/[\\/]/).pop() || "Video renderizado";
  video.src = `/api/video?path=${encodeURIComponent(videoPath)}`;
  modal.hidden = false;
  video.load();
  video.play().catch(() => {});
  refreshIcons();
}

function closeVideoPlayer() {
  const modal = $("#videoPlayerModal");
  const video = $("#nativeVideoPlayer", modal);
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
  if (modal) modal.hidden = true;
}

async function confirmBatchSetup() {
  const modal = $("#batchSetupModal");
  if (!modal) return;
  const scope = modal.dataset.scope || "all";
  const batchMode = $("input[name=batchMode]:checked", modal)?.value || "automatic";
  const batchNames = Object.fromEntries($$(".batch-name-input", modal).map(input => [input.dataset.offerId, input.value.trim()]));
  if (batchMode === "custom" && Object.values(batchNames).some(name => !name)) return showError(new Error("Informe o nome do lote para cada oferta incluida."));
  try {
    await api("/api/production/batch", "POST", { scope, batch_mode: batchMode, batch_names: batchMode === "custom" ? batchNames : {} });
    closeBatchSetup();
    showToast(scope === "active" ? "Producao desta oferta iniciada." : "Producao de todas as ofertas iniciada.");
    watchJob();
  } catch (error) { showError(error); }
}

async function startProduction(mode, scope = "all") {
  if (mode === "batch") return openBatchSetup(scope);
  const copyIds = [...selectedIds];
  if (copyIds.length !== 1) return showError(new Error("Selecione exatamente uma copy para testar."));
  try { await api("/api/production/test", "POST", { copy_ids: copyIds }); showToast("Teste iniciado."); watchJob(); } catch (error) { showError(error); }
}
function watchJob() { clearInterval(jobTimer); jobTimer = setInterval(async () => { try { const job = await api("/api/job"); renderJobStatus(job); if (!job.running) { clearInterval(jobTimer); await loadState(); if (job.error) showError(new Error(job.error)); } } catch (error) { clearInterval(jobTimer); showError(error); } }, 800); }
function renderJobStatus(job) { let bar = $(".job-bar"); if (!bar) { bar = document.createElement("div"); bar.className = "job-bar"; document.body.append(bar); } bar.innerHTML = `<div class="job-top"><span>${escapeHtml(job.status || "Processando")}</span><span>${job.progress || 0}%</span></div><div class="job-progress"><span style="width:${job.progress || 0}%"></span></div>`; if (!job.running) setTimeout(() => bar.remove(), 3000); $("#engineStatus").textContent = job.running ? "Renderizando" : "Pronto"; }

function showView(view) {
  activeView = view;
  document.body.classList.toggle("edit-active", view === "edit");
  $$(".view").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  const config = views[view];
  $("#pageTitle").textContent = config.title;
  $("#sectionKicker").textContent = config.kicker;
  const action = $("#topAction");
  action.hidden = view === "creative" || view === "headline-studio";
  action.innerHTML = `<i data-lucide="${config.icon}"></i>${config.action}`;
  action.onclick = view === "creative" ? createCopy : view === "offers" ? createOffer : saveSettings;
  refreshIcons();
  if (view === "edit") requestAnimationFrame(syncPreview);
}
function showSaved(label = "Salvo localmente") { $("#saveIndicator").innerHTML = `<i data-lucide="check"></i>${label}`; refreshIcons(); }
function showToast(message, kind = "") { const toast = $("#toast"); toast.textContent = message; toast.className = `toast visible ${kind}`; clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.className = "toast", 3200); }
function showError(error) { showToast(error.message || "Ocorreu um erro.", "error"); }
function captionPreviewText(settings) {
  const text = settings.subtitle_mode === "highlight" ? "esta <em>legenda</em> fica" : "esta legenda fica";
  return settings.subtitle_force_caps ? text.toUpperCase() : text;
}
function setSidebarCollapsed(collapsed) {
  const shell = $(".app-shell");
  const toggle = $("#sidebarToggle");
  if (!shell || !toggle) return;
  shell.classList.toggle("sidebar-collapsed", collapsed);
  toggle.setAttribute("aria-label", collapsed ? "Expandir barra lateral" : "Recolher barra lateral");
  toggle.title = collapsed ? "Expandir barra lateral" : "Recolher barra lateral";
  toggle.innerHTML = `<i data-lucide="${collapsed ? "panel-left-open" : "panel-left-close"}"></i>`;
  localStorage.setItem("creative-hub-sidebar-collapsed", String(collapsed));
  refreshIcons();
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character])); }
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function numberSetting(value, fallback) { const number = Number(value); return Number.isFinite(number) ? number : fallback; }
function refreshIcons() { window.lucide?.createIcons({ attrs: { "stroke-width": 1.7 } }); }

$$(".nav-item[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
$("#sidebarToggle").addEventListener("click", () => setSidebarCollapsed(!$(".app-shell").classList.contains("sidebar-collapsed")));
setSidebarCollapsed(localStorage.getItem("creative-hub-sidebar-collapsed") === "true");
$("#settingsToggle").addEventListener("click", () => {
  const menu = $("#settingsMenu");
  if ($(".app-shell").classList.contains("sidebar-collapsed")) {
    menu.classList.remove("open");
    $("#settingsToggle").setAttribute("aria-expanded", "false");
    showView("integrations");
    return;
  }
  const expanded = !menu.classList.contains("open");
  menu.classList.toggle("open", expanded);
  $("#settingsToggle").setAttribute("aria-expanded", String(expanded));
});
$("#topAction").addEventListener("click", createCopy);
$("#openOutputButton").addEventListener("click", () => api("/api/open-output", "POST", {}).catch(showError));
$("#offerModalClose").addEventListener("click", closeOfferModal);
$("#offerModalCancel").addEventListener("click", closeOfferModal);
$("#offerModalConfirm").addEventListener("click", confirmOfferModal);
$("#offerModal").addEventListener("click", event => { if (event.target === event.currentTarget) closeOfferModal(); });
$("#offerNameInput").addEventListener("keydown", event => { if (event.key === "Enter") confirmOfferModal(); });
window.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  if (!$("#offerModal").hidden) closeOfferModal();
  if (!$("#batchSetupModal")?.hidden) closeBatchSetup();
  if (!$("#videoPlayerModal")?.hidden) closeVideoPlayer();
});
loadState().catch(showError);
