const fields = {
  inputFolder: document.querySelector("#inputFolder"),
  outputFolder: document.querySelector("#outputFolder"),
  thresholdDb: document.querySelector("#thresholdDb"),
  silenceDuration: document.querySelector("#silenceDuration"),
  startPadding: document.querySelector("#startPadding"),
  endPadding: document.querySelector("#endPadding"),
  detectionMode: document.querySelector("#detectionMode"),
  subtitleMode: document.querySelector("#subtitleMode"),
  subtitleXPosition: document.querySelector("#subtitleXPosition"),
  subtitleYPosition: document.querySelector("#subtitleYPosition"),
  subtitleFontSize: document.querySelector("#subtitleFontSize"),
  subtitleWordsPerLine: document.querySelector("#subtitleWordsPerLine"),
  subtitleForceCaps: document.querySelector("#subtitleForceCaps"),
  creativeAudioFolder: document.querySelector("#creativeAudioFolder"),
  creativeBrollPath: document.querySelector("#creativeBrollPath"),
  creativeKeywords: document.querySelector("#creativeKeywords"),
  creativeSegmentDuration: document.querySelector("#creativeSegmentDuration"),
  creativeBackgroundSpeedPreset: document.querySelector("#creativeBackgroundSpeedPreset"),
  creativeBackgroundSpeedCustom: document.querySelector("#creativeBackgroundSpeedCustom"),
  creativeSpeedBroll: document.querySelector("#creativeSpeedBroll"),
  creativeTrimAudioEdges: document.querySelector("#creativeTrimAudioEdges"),
  creativeCutInternalSilence: document.querySelector("#creativeCutInternalSilence"),
  creativeSilenceThresholdDb: document.querySelector("#creativeSilenceThresholdDb"),
  creativeMinSilenceDuration: document.querySelector("#creativeMinSilenceDuration"),
  creativeKeepSilence: document.querySelector("#creativeKeepSilence"),
};

const analyzeBtn = document.querySelector("#analyzeBtn");
const processBtn = document.querySelector("#processBtn");
const creativeTranscribeBtn = document.querySelector("#creativeTranscribeBtn");
const creativeTestBtn = document.querySelector("#creativeTestBtn");
const clipsBody = document.querySelector("#clipsBody");
const result = document.querySelector("#result");
const statusBox = document.querySelector("#statusBox");
const statusText = document.querySelector("#statusText");
const bar = document.querySelector("#bar");
const previewCaption = document.querySelector("#previewCaption");
const captionPreview = document.querySelector(".captionPreview");
const modeTabs = document.querySelectorAll(".modeTab");
const pathPickerButtons = document.querySelectorAll(".pathPicker");
const mergeOnlySections = document.querySelectorAll(".mergeOnly");
const creativeOnlySections = document.querySelectorAll(".creativeOnly");
const heroCopy = document.querySelector("#heroCopy");
const inputFolderText = document.querySelector("#inputFolderText");
const modeNote = document.querySelector("#modeNote");
const metricOneLabel = document.querySelector("#metricOneLabel");
const metricTwoLabel = document.querySelector("#metricTwoLabel");
const metricThreeLabel = document.querySelector("#metricThreeLabel");
const tableHeaders = [
  document.querySelector("#thOne"),
  document.querySelector("#thTwo"),
  document.querySelector("#thThree"),
  document.querySelector("#thFour"),
  document.querySelector("#thFive"),
  document.querySelector("#thSix"),
];
let workflowMode = "merge";
let captionDragMode = null;
let captionResizeStart = null;

function seconds(value) {
  return `${Number(value).toFixed(2)}s`;
}

function payload() {
  const customSpeed = fields.creativeBackgroundSpeedCustom.value.trim();
  return {
    input_folder: fields.inputFolder.value.trim(),
    output_folder: fields.outputFolder.value.trim(),
    threshold_db: Number(fields.thresholdDb.value),
    silence_duration: Number(fields.silenceDuration.value),
    start_padding: Number(fields.startPadding.value),
    end_padding: Number(fields.endPadding.value),
    detection_mode: fields.detectionMode.value,
    subtitle_mode: fields.subtitleMode.value,
    subtitle_x_position: Number(fields.subtitleXPosition.value),
    subtitle_y_position: Number(fields.subtitleYPosition.value),
    subtitle_font_size: Number(fields.subtitleFontSize.value),
    subtitle_words_per_line: Number(fields.subtitleWordsPerLine.value),
    subtitle_force_caps: fields.subtitleForceCaps.checked,
    creative_audio_folder: fields.creativeAudioFolder.value.trim(),
    creative_broll_path: fields.creativeBrollPath.value.trim(),
    creative_keywords: fields.creativeKeywords.value.trim(),
    creative_segment_duration: Number(fields.creativeSegmentDuration.value || 3),
    creative_background_speed: Number(customSpeed || fields.creativeBackgroundSpeedPreset.value || 1),
    creative_speed_broll: fields.creativeSpeedBroll.checked,
    creative_trim_audio_edges: fields.creativeTrimAudioEdges.checked,
    creative_cut_internal_silence: fields.creativeCutInternalSilence.checked,
    creative_silence_threshold_db: Number(fields.creativeSilenceThresholdDb.value || -35),
    creative_min_silence_duration: Number(fields.creativeMinSilenceDuration.value || 0.4),
    creative_keep_silence: Number(fields.creativeKeepSilence.value || 0.18),
  };
}

async function pickFolder(button) {
  const targetName = button.dataset.pathTarget;
  const target = fields[targetName];
  if (!target) {
    return;
  }
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "...";
  try {
    const data = await postJson("/api/select-folder", { current_path: target.value.trim() });
    if (data.path) {
      target.value = data.path;
    }
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

function updateCaptionPreview() {
  const x = Number(fields.subtitleXPosition.value || 0.5) * 100;
  const y = Number(fields.subtitleYPosition.value || 0.66) * 100;
  const previewWidth = captionPreview.getBoundingClientRect().width || 360;
  const scale = previewWidth / 720;
  const size = Math.max(6, Number(fields.subtitleFontSize.value || 24) * scale);
  previewCaption.style.left = `${x}%`;
  previewCaption.style.top = `${y}%`;
  previewCaption.style.fontSize = `${size}px`;
  previewCaption.classList.toggle("highlight", fields.subtitleMode.value === "highlight");
  previewCaption.classList.toggle("disabled", fields.subtitleMode.value === "none");
}

function moveCaptionToPointer(event) {
  const rect = captionPreview.getBoundingClientRect();
  const x = Math.min(0.95, Math.max(0.05, (event.clientX - rect.left) / rect.width));
  const y = Math.min(0.95, Math.max(0.05, (event.clientY - rect.top) / rect.height));
  fields.subtitleXPosition.value = x.toFixed(2);
  fields.subtitleYPosition.value = y.toFixed(2);
  updateCaptionPreview();
}

function resizeCaptionFromPointer(event) {
  if (!captionResizeStart) {
    return;
  }
  const delta = event.clientX - captionResizeStart.x - (event.clientY - captionResizeStart.y);
  const nextSize = Math.min(72, Math.max(12, captionResizeStart.fontSize + delta * 0.16));
  fields.subtitleFontSize.value = String(Math.round(nextSize));
  updateCaptionPreview();
}

function setBusy(isBusy, message = "Pronto") {
  analyzeBtn.disabled = isBusy;
  processBtn.disabled = isBusy;
  creativeTranscribeBtn.disabled = isBusy;
  creativeTestBtn.disabled = isBusy;
  statusText.textContent = message;
}

function setMode(mode) {
  workflowMode = mode;
  const isCaptionOnly = mode === "caption";
  const isCreative = mode === "creative";
  document.body.dataset.mode = mode;
  modeTabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  mergeOnlySections.forEach((section) => {
    section.classList.toggle("hidden", mode !== "merge");
  });
  creativeOnlySections.forEach((section) => {
    section.classList.toggle("hidden", !isCreative);
  });
  if (isCreative) {
    heroCopy.textContent = "Monta criativos em lote: áudio da copy, takes aleatórios, B-roll por palavra-chave e legenda automática.";
    modeNote.textContent = "Criativos em lote com áudio, banco de takes, B-roll e legenda.";
  } else if (isCaptionOnly) {
    heroCopy.textContent = "Pega todos os vídeos de uma pasta, cria a legenda pelo áudio de cada um e exporta cópias legendadas sem mexer nos originais.";
    modeNote.textContent = "Legenda vários vídeos de uma pasta sem juntar takes.";
  } else {
    heroCopy.textContent = "Corta silêncio no começo e no fim dos takes, junta tudo e exporta um vídeo final sem mexer nos arquivos originais.";
    modeNote.textContent = "Motor rápido para limpar takes e montar um vídeo único.";
  }
  inputFolderText.textContent = isCaptionOnly ? "Pasta dos vídeos" : "Pasta dos takes";
  analyzeBtn.classList.toggle("hidden", mode !== "merge");
  creativeTranscribeBtn.classList.toggle("hidden", !isCreative);
  creativeTestBtn.classList.toggle("hidden", !isCreative);
  processBtn.textContent = isCreative ? "Processar lote" : isCaptionOnly ? "Legendar todos" : "Gerar vídeo final";
  if ((isCaptionOnly || isCreative) && fields.subtitleMode.value === "none") {
    fields.subtitleMode.value = "normal";
    updateCaptionPreview();
  }
  resetReport();
}

function resetReport() {
  if (workflowMode === "caption") {
    metricOneLabel.textContent = "Vídeos";
    metricTwoLabel.textContent = "Legendados";
    metricThreeLabel.textContent = "Falhas";
    document.querySelector("#originalDuration").textContent = "--";
    document.querySelector("#finalDuration").textContent = "--";
    document.querySelector("#removedDuration").textContent = "--";
    tableHeaders[0].textContent = "Vídeo";
    tableHeaders[1].textContent = "Status";
    tableHeaders[2].textContent = "Palavras";
    tableHeaders[3].textContent = "Saída";
    tableHeaders[4].textContent = "Legenda";
    tableHeaders[5].textContent = "Erro";
    clipsBody.innerHTML = `<tr><td colspan="6">Clique em legendar todos para processar a pasta.</td></tr>`;
  } else if (workflowMode === "creative") {
    metricOneLabel.textContent = "Áudios";
    metricTwoLabel.textContent = "Prontos";
    metricThreeLabel.textContent = "Falhas";
    document.querySelector("#originalDuration").textContent = "--";
    document.querySelector("#finalDuration").textContent = "--";
    document.querySelector("#removedDuration").textContent = "--";
    tableHeaders[0].textContent = "Áudio";
    tableHeaders[1].textContent = "Status";
    tableHeaders[2].textContent = "Duração";
    tableHeaders[3].textContent = "Gatilho";
    tableHeaders[4].textContent = "Saída";
    tableHeaders[5].textContent = "Erro";
    clipsBody.innerHTML = `<tr><td colspan="6">Transcreva um áudio, gere um teste ou processe o lote.</td></tr>`;
  } else {
    metricOneLabel.textContent = "Originais";
    metricTwoLabel.textContent = "Final estimado";
    metricThreeLabel.textContent = "Cortado";
    document.querySelector("#originalDuration").textContent = "--";
    document.querySelector("#finalDuration").textContent = "--";
    document.querySelector("#removedDuration").textContent = "--";
    tableHeaders[0].textContent = "Take";
    tableHeaders[1].textContent = "Início";
    tableHeaders[2].textContent = "Fim";
    tableHeaders[3].textContent = "Usa";
    tableHeaders[4].textContent = "Corta";
    tableHeaders[5].textContent = "Método";
    clipsBody.innerHTML = `<tr><td colspan="6">Clique em analisar para ver os cortes.</td></tr>`;
  }
}

function setSummary(data) {
  document.querySelector("#originalDuration").textContent = seconds(data.original_duration);
  document.querySelector("#finalDuration").textContent = seconds(data.final_duration);
  document.querySelector("#removedDuration").textContent = seconds(data.removed_duration);
}

function setBatchSummary(data) {
  document.querySelector("#originalDuration").textContent = String(data.total);
  document.querySelector("#finalDuration").textContent = String(data.completed);
  document.querySelector("#removedDuration").textContent = String(data.failed);
}

function setRows(clips) {
  clipsBody.innerHTML = "";
  for (const clip of clips) {
    const row = document.createElement("tr");
    const method = clip.detection_method === "speech" ? `Fala (${clip.words_detected})` : "Volume";
    row.innerHTML = `
      <td title="${clip.name}">${clip.name}</td>
      <td>${seconds(clip.start)}</td>
      <td>${seconds(clip.end)}</td>
      <td>${seconds(clip.kept_duration)}</td>
      <td>${seconds(clip.removed_duration)}</td>
      <td>${method}</td>
    `;
    clipsBody.appendChild(row);
  }
}

function filenameFromPath(path) {
  return String(path || "").split(/[\\/]/).pop();
}

function setBatchRows(items) {
  clipsBody.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("tr");
    const ok = item.status === "completed";
    const output = item.output_path
      ? `<a href="${item.video_url}" target="_blank" rel="noreferrer">${filenameFromPath(item.output_path)}</a>`
      : "--";
    const subtitle = item.subtitle_path ? filenameFromPath(item.subtitle_path) : "--";
    row.innerHTML = `
      <td title="${filenameFromPath(item.source_path)}">${filenameFromPath(item.source_path)}</td>
      <td><span class="pill ${ok ? "ok" : "bad"}">${ok ? "Pronto" : "Falhou"}</span></td>
      <td>${item.words_detected}</td>
      <td>${output}</td>
      <td>${subtitle}</td>
      <td title="${item.error || ""}">${item.error || "--"}</td>
    `;
    clipsBody.appendChild(row);
  }
}

function setCreativeRows(items) {
  clipsBody.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("tr");
    const ok = item.status === "completed";
    const output = item.output_path
      ? `<a href="${item.video_url}" target="_blank" rel="noreferrer">${filenameFromPath(item.output_path)}</a>`
      : "--";
    const trigger = item.trigger_word ? `${item.trigger_word} (${seconds(item.trigger_time || 0)})` : "--";
    row.innerHTML = `
      <td title="${filenameFromPath(item.audio_path)}">${filenameFromPath(item.audio_path)}</td>
      <td><span class="pill ${ok ? "ok" : "bad"}">${ok ? "Pronto" : "Falhou"}</span></td>
      <td>${seconds(item.duration)}</td>
      <td>${trigger}</td>
      <td>${output}</td>
      <td title="${item.error || ""}">${item.error || "--"}</td>
    `;
    clipsBody.appendChild(row);
  }
}

function showError(message) {
  statusBox.classList.add("error");
  statusText.textContent = "Erro";
  result.classList.remove("hidden");
  result.textContent = message;
}

async function postJson(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "Não foi possível concluir.");
  }
  return body;
}

async function openOutputFolder() {
  await postJson("/api/open-output", payload());
}

async function openVideo(videoPath) {
  await postJson("/api/open-video", { ...payload(), video_path: videoPath });
}

async function analyze() {
  result.classList.add("hidden");
  statusBox.classList.remove("error");
  bar.style.width = "18%";
  setBusy(true, "Analisando takes...");
  try {
    const data = await postJson("/api/analyze", payload());
    setSummary(data);
    setRows(data.clips);
    bar.style.width = "100%";
    setBusy(false, "Análise pronta");
  } catch (error) {
    bar.style.width = "0%";
    setBusy(false, "Pronto");
    showError(error.message);
  }
}

async function pollJob() {
  const response = await fetch("/api/job");
  const data = await response.json();
  statusText.textContent = data.status;
  bar.style.width = `${data.progress || 0}%`;
  if (data.error) {
    setBusy(false, "Pronto");
    showError(data.error.split("\n")[0]);
    return;
  }
  if (data.running) {
    window.setTimeout(pollJob, 1000);
    return;
  }
  if (data.result) {
    if (data.result.kind === "caption_batch") {
      setBusy(false, "Lote finalizado");
      setBatchSummary(data.result);
      setBatchRows(data.result.items);
      const firstVideo = data.result.items.find((item) => item.output_path);
      result.classList.remove("hidden");
      result.innerHTML = `
        Finalizado: ${data.result.completed}/${data.result.total} vídeos legendados<br>
        Relatório: ${data.result.report_path}
        <div class="resultActions">
          <button class="small" id="openVideoBtn" ${firstVideo ? "" : "disabled"}>Abrir primeiro vídeo</button>
          <button class="small secondary" id="openFolderBtn">Abrir pasta</button>
        </div>
      `;
      if (firstVideo) {
        document.querySelector("#openVideoBtn").addEventListener("click", () => openVideo(firstVideo.output_path));
      }
      document.querySelector("#openFolderBtn").addEventListener("click", openOutputFolder);
    } else if (data.result.kind === "creative_batch") {
      setBusy(false, data.result.test_only ? "Teste finalizado" : "Criativos finalizados");
      setBatchSummary(data.result);
      setCreativeRows(data.result.items);
      const firstVideo = data.result.items.find((item) => item.output_path);
      result.classList.remove("hidden");
      result.innerHTML = `
        Finalizado: ${data.result.completed}/${data.result.total} criativos prontos<br>
        Relatório: ${data.result.report_path}<br>
        Histórico de cortes: ${data.result.history_path}
        <div class="resultActions">
          <button class="small" id="openVideoBtn" ${firstVideo ? "" : "disabled"}>Abrir primeiro vídeo</button>
          <button class="small secondary" id="openFolderBtn">Abrir pasta</button>
        </div>
      `;
      if (firstVideo) {
        document.querySelector("#openVideoBtn").addEventListener("click", () => openVideo(firstVideo.output_path));
      }
      document.querySelector("#openFolderBtn").addEventListener("click", openOutputFolder);
    } else {
      setBusy(false, "Vídeo finalizado");
      setSummary(data.result);
      setRows(data.result.clips);
      const subtitleLine = data.result.subtitle_path ? `<br>Legenda: ${data.result.subtitle_path}` : "";
      result.classList.remove("hidden");
      result.innerHTML = `
        Pronto: <a href="${data.result.video_url}" target="_blank" rel="noreferrer">abrir vídeo final no navegador</a><br>
        ${data.result.output_path}
        ${subtitleLine}
        <div class="resultActions">
          <button class="small" id="openVideoBtn">Abrir vídeo</button>
          <button class="small secondary" id="openFolderBtn">Abrir pasta</button>
        </div>
      `;
      document.querySelector("#openVideoBtn").addEventListener("click", () => openVideo(data.result.output_path));
      document.querySelector("#openFolderBtn").addEventListener("click", openOutputFolder);
    }
  }
}

async function transcribeCreative() {
  result.classList.add("hidden");
  statusBox.classList.remove("error");
  bar.style.width = "8%";
  setBusy(true, "Transcrevendo primeiro áudio...");
  try {
    const data = await postJson("/api/creative-transcribe", payload());
    bar.style.width = "100%";
    setBusy(false, "Transcrição pronta");
    result.classList.remove("hidden");
    result.innerHTML = `
      Áudio: ${data.audio_path}<br>
      Palavras detectadas: ${data.words_count}<br>
      <div class="transcript">${data.text || "--"}</div>
    `;
  } catch (error) {
    bar.style.width = "0%";
    setBusy(false, "Pronto");
    showError(error.message);
  }
}

async function processCreativeTest() {
  result.classList.add("hidden");
  statusBox.classList.remove("error");
  setBusy(true, "Preparando teste...");
  bar.style.width = "5%";
  try {
    await postJson("/api/creative-test", payload());
    pollJob();
  } catch (error) {
    setBusy(false, "Pronto");
    showError(error.message);
  }
}

async function processVideo() {
  result.classList.add("hidden");
  statusBox.classList.remove("error");
  setBusy(true, "Preparando...");
  bar.style.width = "5%";
  try {
    const endpoint = workflowMode === "creative"
      ? "/api/creative-batch"
      : workflowMode === "caption"
        ? "/api/caption-batch"
        : "/api/process";
    await postJson(endpoint, payload());
    pollJob();
  } catch (error) {
    setBusy(false, "Pronto");
    showError(error.message);
  }
}

async function boot() {
  const response = await fetch("/api/defaults");
  const defaults = await response.json();
  fields.inputFolder.value = defaults.input_folder;
  fields.outputFolder.value = defaults.output_folder;
  fields.thresholdDb.value = defaults.threshold_db;
  fields.silenceDuration.value = defaults.silence_duration;
  fields.startPadding.value = defaults.start_padding;
  fields.endPadding.value = defaults.end_padding;
  fields.detectionMode.value = defaults.detection_mode;
  fields.subtitleMode.value = defaults.subtitle_mode;
  fields.subtitleXPosition.value = defaults.subtitle_x_position;
  fields.subtitleYPosition.value = defaults.subtitle_y_position;
  fields.subtitleFontSize.value = defaults.subtitle_font_size;
  fields.subtitleWordsPerLine.value = defaults.subtitle_words_per_line;
  fields.subtitleForceCaps.checked = defaults.subtitle_force_caps;
  fields.creativeAudioFolder.value = defaults.creative_audio_folder;
  fields.creativeBrollPath.value = defaults.creative_broll_path;
  fields.creativeKeywords.value = defaults.creative_keywords;
  fields.creativeSegmentDuration.value = defaults.creative_segment_duration;
  const defaultSpeed = String(defaults.creative_background_speed);
  const presetOption = Array.from(fields.creativeBackgroundSpeedPreset.options).some((option) => option.value === defaultSpeed);
  fields.creativeBackgroundSpeedPreset.value = presetOption ? defaultSpeed : "1";
  fields.creativeBackgroundSpeedCustom.value = presetOption ? "" : defaultSpeed;
  fields.creativeSpeedBroll.checked = defaults.creative_speed_broll;
  fields.creativeTrimAudioEdges.checked = defaults.creative_trim_audio_edges;
  fields.creativeCutInternalSilence.checked = defaults.creative_cut_internal_silence;
  fields.creativeSilenceThresholdDb.value = defaults.creative_silence_threshold_db;
  fields.creativeMinSilenceDuration.value = defaults.creative_min_silence_duration;
  fields.creativeKeepSilence.value = defaults.creative_keep_silence;
  updateCaptionPreview();
  resetReport();
}

analyzeBtn.addEventListener("click", analyze);
processBtn.addEventListener("click", processVideo);
creativeTranscribeBtn.addEventListener("click", transcribeCreative);
creativeTestBtn.addEventListener("click", processCreativeTest);
fields.creativeBackgroundSpeedPreset.addEventListener("change", () => {
  fields.creativeBackgroundSpeedCustom.value = "";
});
pathPickerButtons.forEach((button) => {
  button.addEventListener("click", () => pickFolder(button));
});
modeTabs.forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
fields.subtitleMode.addEventListener("change", updateCaptionPreview);
fields.subtitleXPosition.addEventListener("input", updateCaptionPreview);
fields.subtitleYPosition.addEventListener("input", updateCaptionPreview);
fields.subtitleFontSize.addEventListener("input", updateCaptionPreview);
window.addEventListener("resize", updateCaptionPreview);
captionPreview.addEventListener("pointerdown", (event) => {
  captionDragMode = event.target.closest(".captionSizeHandle") ? "resize" : "move";
  captionPreview.setPointerCapture(event.pointerId);
  if (captionDragMode === "resize") {
    captionResizeStart = {
      x: event.clientX,
      y: event.clientY,
      fontSize: Number(fields.subtitleFontSize.value || 24),
    };
  } else {
    moveCaptionToPointer(event);
  }
});
captionPreview.addEventListener("pointermove", (event) => {
  if (captionDragMode === "move") {
    moveCaptionToPointer(event);
  } else if (captionDragMode === "resize") {
    resizeCaptionFromPointer(event);
  }
});
captionPreview.addEventListener("pointerup", (event) => {
  captionDragMode = null;
  captionResizeStart = null;
  captionPreview.releasePointerCapture(event.pointerId);
});
captionPreview.addEventListener("pointercancel", () => {
  captionDragMode = null;
  captionResizeStart = null;
});
boot();
