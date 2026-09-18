# Lote De Criativos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir todas as copies em lote com narracao paralela, reaproveitamento verificavel de artefatos e arquivos nomeados pelo titulo da copy.

**Architecture:** Um modulo de artefatos calcula nomes seguros e assinaturas deterministicas por etapa. Um coordenador de producao cria audios em paralelo e envia cada audio concluido para a ponte de video, que passa a aceitar caminhos finais e um carregador de transcricao em cache. O `HubService` expoe o coordenador como um unico job e o frontend separa claramente lote global de teste da copy selecionada.

**Tech Stack:** Python 3 standard library (`hashlib`, `json`, `concurrent.futures`, `threading`), HTTP server local, JavaScript sem framework, FFmpeg e o motor existente `video_edit_mvp`.

**Spec:** `docs/superpowers/specs/2026-09-16-lote-de-criativos-design.md`

## Global Constraints

- Nunca editar `C:\FabricaDeVideos`; a fabrica original permanece somente como referencia.
- `Gerar lote` processa todas as copies com texto, independente da selecao visual.
- `Testar selecionado` aceita exatamente uma copy selecionada.
- Reutilizar artefatos somente quando a assinatura persistida coincide e o arquivo existe.
- Detectar arquivos apagados manualmente e recriar somente as etapas afetadas.
- Usar nomes validos no Windows e preservar um titulo legivel, com sufixo estavel para duplicatas.
- Limitar a concorrencia de narracoes; renderizacao continua serial para nao multiplicar processos FFmpeg pesados.
- Nao adicionar dependencias de terceiros.

---

## File Structure

- Create: `creative_hub/artifacts.py` - nomes Windows-safe, assinaturas e verificacao de artefatos.
- Create: `creative_hub/production.py` - coordenacao de audio paralelo, cache e renderizacao por copy.
- Modify: `creative_hub/domain.py` - metadados de assinatura e caminho de transcricao em `CopyCard`.
- Modify: `creative_hub/voice_provider.py` - destino organizado de audio sem nome aleatorio.
- Modify: `creative_hub/video_bridge.py` - renderizacao de uma copy com destino e transcricao definidos.
- Modify: `video_edit_mvp/creative_engine.py` - hooks retrocompativeis de transcricao e caminhos de saida.
- Modify: `creative_hub/app.py` - endpoints de producao e atualizacao segura do job.
- Modify: `creative_hub/web/app.js` - selecionar todas, limpar selecao e novos comandos de lote/teste.
- Modify: `creative_hub/web/styles.css` - controles compactos da barra de criativos.
- Create: `creative_hub/tests/test_artifacts.py` - cobertura de assinatura, nomes e arquivos ausentes.
- Create: `creative_hub/tests/test_production.py` - cobertura de concorrencia, cache e isolamento de falhas.
- Modify: `creative_hub/tests/test_app_api.py` - rotas, regra de teste selecionado e persistencia.
- Modify: `creative_hub/tests/test_video_bridge.py` - renderizacao com nome e transcricao cacheada.
- Modify: `video_edit_mvp/tests/test_creative_engine.py` - hooks opcionais sem alterar o comportamento legado.
- Modify: `creative_hub/tests/test_web_ui.py` - controles de selecao e rotas frontend.

### Task 1: Persisted Artifact Contract

**Files:**
- Create: `creative_hub/artifacts.py`
- Modify: `creative_hub/domain.py:8-90`
- Create: `creative_hub/tests/test_artifacts.py`
- Modify: `creative_hub/tests/test_domain.py`

**Interfaces:**
- Produces `ArtifactPlan.from_card(card: CopyCard, settings: HubSettings) -> ArtifactPlan`.
- Produces `ArtifactPlan.audio_path`, `transcript_path`, `video_path`, `audio_signature`, `transcript_signature`, and `render_signature`.
- Produces `artifact_is_current(path: str | None, stored_signature: str | None, expected_signature: str) -> bool`.
- Extends `CopyCard` with `transcript_path`, `audio_signature`, `transcript_signature`, and `render_signature` as optional persisted strings.

- [ ] **Step 1: Write failing artifact tests**

```python
def test_artifact_plan_uses_a_windows_safe_title_and_stable_duplicate_suffix(tmp_path):
    card = CopyCard(id="abcd1234ef", title='Video: 22 / oferta?', text="Copy")
    plan = ArtifactPlan.from_card(card, HubSettings(output_folder=str(tmp_path)))

    assert plan.audio_path == tmp_path / "audios" / "Video 22 oferta_abcd1234.mp3"
    assert plan.transcript_path == tmp_path / "transcricoes" / "Video 22 oferta_abcd1234.json"
    assert plan.video_path == tmp_path / "Video 22 oferta_abcd1234.mp4"

def test_artifact_is_not_current_when_the_file_was_deleted(tmp_path):
    path = tmp_path / "audio.mp3"
    assert not artifact_is_current(str(path), "signature", "signature")
```

- [ ] **Step 2: Run the new artifact tests and confirm they fail**

Run: `python -m unittest tests.test_artifacts -v`

Expected: FAIL because `artifacts` and the new fields do not exist.

- [ ] **Step 3: Implement deterministic artifact planning**

```python
@dataclass(frozen=True)
class ArtifactPlan:
    audio_path: Path
    transcript_path: Path
    video_path: Path
    audio_signature: str
    transcript_signature: str
    render_signature: str

    @classmethod
    def from_card(cls, card: CopyCard, settings: HubSettings) -> "ArtifactPlan":
        stem = safe_copy_stem(card)
        output = Path(settings.output_folder)
        audio_signature = payload_signature({"text": card.text, "voice": effective_voice(card, settings), "provider": settings.voice_provider})
        transcript_signature = payload_signature({"audio": audio_signature, "provider": settings.transcription_provider, "audio_edit": audio_edit_payload(settings)})
        render_signature = payload_signature({"transcript": transcript_signature, "render": render_payload(settings)})
        return cls(output / "audios" / f"{stem}.mp3", output / "transcricoes" / f"{stem}.json", output / f"{stem}.mp4", audio_signature, transcript_signature, render_signature)
```

Use `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` before SHA-256. Include text, voice effective, voice provider in the audio signature; include audio signature, transcription provider and audio-edit settings in the transcript signature; include transcript signature plus all rendering settings in the render signature.

- [ ] **Step 4: Extend serialization without exposing secrets**

Add the four fields to `CopyCard`, `copy_from_dict`, and `copy_to_dict`. Keep old state files valid by supplying `None` defaults.

- [ ] **Step 5: Run artifact and domain tests**

Run: `python -m unittest tests.test_artifacts tests.test_domain -v`

Expected: PASS with a legacy state fixture still loading.

### Task 2: Stable Voice Output Paths

**Files:**
- Modify: `creative_hub/voice_provider.py:45-190`
- Modify: `creative_hub/tests/test_voice_provider.py`

**Interfaces:**
- Changes `VoiceProvider.generate` to accept `destination: Path | None = None` after `progress_callback`.
- `OpenSpeakerVoiceProvider.generate` writes the downloaded audio to `destination` when supplied, otherwise keeps the current compatibility behavior.

- [ ] **Step 1: Write the failing destination test**

```python
def test_generate_uses_the_requested_organized_destination(tmp_path):
    provider = OpenSpeakerVoiceProvider(transport=fake_transport)
    destination = tmp_path / "audios" / "Video 22_abcd1234.mp3"

    result = provider.generate(card, settings, destination=destination)

    assert result == destination
    assert destination.read_bytes() == b"audio"
```

- [ ] **Step 2: Run the voice-provider test and confirm it fails**

Run: `python -m unittest tests.test_voice_provider.OpenSpeakerVoiceProviderTests.test_generate_uses_the_requested_organized_destination -v`

Expected: FAIL because `generate` does not accept `destination`.

- [ ] **Step 3: Implement optional destination handling**

```python
def generate(self, card, settings, progress_callback=None, destination=None):
    # Resolve API URL as today.
    target = destination or self._audio_destination(card, Path(settings.output_folder), audio_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.body)
    return target
```

Update `UnavailableVoiceProvider` and test doubles to use the same optional argument.

- [ ] **Step 4: Run the voice-provider suite**

Run: `python -m unittest tests.test_voice_provider -v`

Expected: PASS, including the legacy random-name fallback test if present.

### Task 3: Engine Hooks For Cached Words And Final Names

**Files:**
- Modify: `video_edit_mvp/creative_engine.py:262-382`
- Modify: `video_edit_mvp/tests/test_creative_engine.py`

**Interfaces:**
- Extends `process_creative_batch` with optional `word_loader: Callable[[Path], list[SpeechWord]] | None = None`.
- Extends `process_creative_batch` with optional `output_paths_for_audio: Callable[[Path], tuple[Path, Path]] | None = None`.
- Existing callers receive identical timestamped names and detector behavior when both hooks are omitted.

- [ ] **Step 1: Write failing compatibility and hook tests**

```python
def test_process_batch_uses_cached_words_and_requested_paths(tmp_path):
    requested_video = tmp_path / "Video 22.mp4"
    requested_ass = tmp_path / "Video 22.ass"
    result = process_creative_batch(
        audio_folder=audio_folder,
        takes_folder=takes,
        output_folder=tmp_path,
        word_loader=lambda _: [SpeechWord("ola", 0.0, 0.2)],
        output_paths_for_audio=lambda _: (requested_video, requested_ass),
        renderer=fake_renderer,
    )

    assert result.items[0].output_path == str(requested_video)
    assert result.items[0].subtitle_path == str(requested_ass)
```

- [ ] **Step 2: Run the focused engine test and confirm it fails**

Run: `python -m unittest tests.test_creative_engine.CreativeEngineTests.test_process_batch_uses_cached_words_and_requested_paths -v`

Expected: FAIL because the optional arguments do not exist.

- [ ] **Step 3: Implement the hooks with legacy defaults**

```python
words = word_loader(effective_audio) if word_loader else detector.detect_words(effective_audio)
if output_paths_for_audio:
    output_path, subtitle_path = output_paths_for_audio(audio)
else:
    output_path = output_folder / f"{audio.stem}_creative_{batch_stamp}.mp4"
    subtitle_path = output_folder / f"{audio.stem}_creative_{batch_stamp}.ass"
```

Keep `limit`, report generation and failure handling unchanged.

- [ ] **Step 4: Run the engine suite**

Run: `python -m unittest discover -s tests`

Expected: PASS from `video_edit_mvp`.

### Task 4: Bridge-Level Transcription Cache And Per-Copy Rendering

**Files:**
- Modify: `creative_hub/video_bridge.py:37-145`
- Modify: `creative_hub/tests/test_video_bridge.py`

**Interfaces:**
- Produces `render_card(card: CopyCard, settings: HubSettings, plan: ArtifactPlan, test_only: bool, process_func=process_creative_batch) -> RenderResult`.
- Produces `CachedWordLoader(plan: ArtifactPlan, detector).load(audio_path: Path) -> list[SpeechWord]`.
- Persists `plan.transcript_path` as JSON with `signature` and timestamped words.

- [ ] **Step 1: Write failing cache tests**

```python
def test_render_card_reuses_matching_transcript_and_writes_named_video(tmp_path):
    plan = ArtifactPlan.from_card(card, settings)
    plan.transcript_path.parent.mkdir(parents=True)
    plan.transcript_path.write_text(json.dumps({"signature": plan.transcript_signature, "words": [{"text": "ola", "start": 0, "end": 1}]}))

    result = render_card(card, settings, plan, test_only=False, process_func=fake_process)

    assert result.output_path == str(plan.video_path)
    assert detector_calls == 0
```

- [ ] **Step 2: Run the focused bridge test and confirm it fails**

Run: `python -m unittest tests.test_video_bridge.VideoBridgeTests.test_render_card_reuses_matching_transcript_and_writes_named_video -v`

Expected: FAIL because `render_card` does not exist.

- [ ] **Step 3: Implement cache loader and named single-card render**

`CachedWordLoader` must only trust JSON when its `signature` matches `plan.transcript_signature`; otherwise detect words, write the JSON atomically through a temporary sibling file, and return the detected words. Stage one audio under a stable card id, invoke the new engine hooks, and write `CopyCard.transcript_path` plus `CopyCard.transcript_signature` after a successful result.

- [ ] **Step 4: Preserve the batch adapter**

Keep `render_cards` as a compatibility adapter that loops cards through `render_card` with fresh `ArtifactPlan` instances. Existing callers and tests must remain usable.

- [ ] **Step 5: Run bridge tests**

Run: `python -m unittest tests.test_video_bridge -v`

Expected: PASS, including the existing AssemblyAI and headline forwarding coverage.

### Task 5: Production Coordinator With Parallel Narration

**Files:**
- Create: `creative_hub/production.py`
- Create: `creative_hub/tests/test_production.py`

**Interfaces:**
- Produces `ProductionCoordinator(voice_provider_factory, render_card, max_voice_workers=3)`.
- Produces `run(cards: list[CopyCard], settings: HubSettings, mode: Literal["batch", "test"], progress: Callable[[str, int, list[dict]], None]) -> list[dict]`.
- `run` returns one result dict per eligible card with `card_id`, `audio`, `transcript`, `video`, `status`, and `reused` stages.

- [ ] **Step 1: Write failing coordination tests**

```python
def test_batch_starts_voice_generation_for_multiple_pending_cards_before_rendering(tmp_path):
    provider = BlockingFakeProvider()
    coordinator = ProductionCoordinator(lambda: provider, fake_render_card, max_voice_workers=2)

    thread = Thread(target=lambda: coordinator.run(cards, settings, "batch", progress_events.append))
    thread.start()
    assert provider.second_generate_started.wait(timeout=2)

def test_coordinator_reuses_existing_audio_video_and_recovers_when_audio_is_deleted(tmp_path):
    plan = ArtifactPlan.from_card(cards[0], settings)
    plan.audio_path.parent.mkdir(parents=True)
    plan.audio_path.write_bytes(b"audio")
    plan.video_path.write_bytes(b"video")
    cards[0].audio_path = str(plan.audio_path)
    cards[0].output_path = str(plan.video_path)
    cards[0].audio_signature = plan.audio_signature
    cards[0].render_signature = plan.render_signature

    coordinator.run(cards[:1], settings, "batch", progress_events.append)
    assert provider.generate_calls == 0
    plan.audio_path.unlink()
    coordinator.run(cards[:1], settings, "batch", progress_events.append)
    assert provider.generate_calls == 1
```

- [ ] **Step 2: Run coordinator tests and confirm they fail**

Run: `python -m unittest tests.test_production -v`

Expected: FAIL because `ProductionCoordinator` does not exist.

- [ ] **Step 3: Implement the pipeline**

Use `ThreadPoolExecutor(max_workers=max_voice_workers)` only for API audio generation. Submit pending API-audio cards, and consume futures with `as_completed`. For each completed audio, immediately call `render_card`; render calls remain on the coordinator thread. Process valid manual audios directly. Before each stage, compare `ArtifactPlan` signatures and `artifact_is_current`; mark reused stages in its result. Catch exceptions per card so one failed copy never stops the rest.

- [ ] **Step 4: Update cards and progress atomically**

After every card result, set `status`, paths, signatures and `error` on the shared card. Emit progress from 0 to 100 using completed cards divided by eligible cards, with messages like `Narrando 2/10`, `Transcrevendo Video 22`, `Renderizando Video 22`, and `Reaproveitado: Video 22`.

- [ ] **Step 5: Run coordinator tests**

Run: `python -m unittest tests.test_production -v`

Expected: PASS, including max-worker, reuse, deleted-file and isolated-failure cases.

### Task 6: Service And API Production Endpoints

**Files:**
- Modify: `creative_hub/app.py:25-235`
- Modify: `creative_hub/tests/test_app_api.py`

**Interfaces:**
- Adds `HubService.start_production(mode: Literal["batch", "test"], copy_ids: list[str]) -> None`.
- Adds `POST /api/production/batch` with an empty payload.
- Adds `POST /api/production/test` with `{ "copy_ids": ["copy-id"] }`.
- Keeps `/api/voice/generate`, `/api/render/test`, and `/api/render/batch` temporarily compatible.

- [ ] **Step 1: Write failing API tests**

```python
def test_batch_endpoint_processes_every_copy_with_text_even_when_none_is_selected(self):
    _, first = self.client.request("POST", "/api/copies", {"title": "Um", "text": "Copy um"})
    _, second = self.client.request("POST", "/api/copies", {"title": "Dois", "text": "Copy dois"})
    first_copy_id = first["copy"]["id"]
    second_copy_id = second["copy"]["id"]

    status, _ = self.client.request("POST", "/api/production/batch", {})

    assert status == 202
    completed = wait_for_job(self.client)["results"]
    assert {item["card_id"] for item in completed} == {first_copy_id, second_copy_id}

def test_test_endpoint_requires_exactly_one_selected_copy(self):
    status, payload = self.client.request("POST", "/api/production/test", {"copy_ids": []})
    assert status == 422
    assert "uma copy" in payload["error"]
```

- [ ] **Step 2: Run the focused API tests and confirm they fail**

Run: `python -m unittest tests.test_app_api.HubApiTests.test_batch_endpoint_processes_every_copy_with_text_even_when_none_is_selected tests.test_app_api.HubApiTests.test_test_endpoint_requires_exactly_one_selected_copy -v`

Expected: FAIL with route not found.

- [ ] **Step 3: Inject and start the coordinator**

Add `production_coordinator_factory` to `HubService` and `create_server` for test injection. `batch` takes `copy for copy in state.copies if copy.text.strip()`. `test` validates one supplied id. Start one daemon thread, set `job["running"]`, and provide the coordinator progress callback with copies of result payloads under `self.lock`.

- [ ] **Step 4: Persist the completed state and preserve partial failures**

When the coordinator returns, call `_save()` under `self.lock`, set `running=False`, `progress=100`, and use `Produção finalizada` or `Produção finalizada com erros` based on per-copy statuses. The top-level job error is only for a coordinator-wide failure.

- [ ] **Step 5: Run API tests**

Run: `python -m unittest tests.test_app_api -v`

Expected: PASS, including existing picker, voice and manual-audio routes.

### Task 7: Batch And Selection Controls In The Interface

**Files:**
- Modify: `creative_hub/web/app.js:61-110, 410-416`
- Modify: `creative_hub/web/styles.css:90-120`
- Modify: `creative_hub/tests/test_web_ui.py`

**Interfaces:**
- `selectAllCopies()` selects every card id in `state.copies`.
- `clearCopySelection()` clears `selectedIds`.
- `startProduction("batch")` posts `{}` to `/api/production/batch`.
- `startProduction("test")` posts selected ids to `/api/production/test` only when exactly one is selected.

- [ ] **Step 1: Write failing UI contract tests**

```python
def test_ui_exposes_global_batch_and_selection_controls(self):
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for token in ["Selecionar todas", "Limpar selecao", "selectAllCopies", "/api/production/batch", "/api/production/test"]:
        self.assertIn(token, script)
```

- [ ] **Step 2: Run the UI test and confirm it fails**

Run: `python -m unittest tests.test_web_ui.WebUiTests.test_ui_exposes_global_batch_and_selection_controls -v`

Expected: FAIL because the controls and routes do not exist.

- [ ] **Step 3: Implement controls and route calls**

Render a compact selection group near the existing toolbar actions. `Gerar lote` calls the batch endpoint with no selected ids. `Testar selecionado` checks `selectedIds.size === 1`, otherwise shows `Selecione exatamente uma copy para testar.`. After starting either job, call the existing `watchJob()` and retain the current job progress panel.

- [ ] **Step 4: Add restrained responsive styles**

Use the existing `.toolbar-actions`, `.secondary-button`, and `.primary-button` visual language. Keep all buttons on one line when space permits and wrap cleanly below 700px without resizing controls based on viewport width.

- [ ] **Step 5: Run UI tests and browser check**

Run: `python -m unittest tests.test_web_ui -v`

Then load `http://127.0.0.1:8092/`, verify `Selecionar todas` marks every card, `Limpar selecao` clears them, and verify `Gerar lote` does not depend on a selection.

### Task 8: Full Regression And Manual Production Verification

**Files:**
- Modify only if regression tests reveal a defect.

**Interfaces:**
- Consumes all preceding public contracts.
- Produces a verified local Creative Hub at `http://127.0.0.1:8092/`.

- [ ] **Step 1: Run all Creative Hub tests**

Run: `python -m unittest discover -s tests`

Expected: PASS.

- [ ] **Step 2: Run all engine tests**

Run: `Push-Location ..\\video_edit_mvp; python -m unittest discover -s tests; Pop-Location`

Expected: PASS.

- [ ] **Step 3: Compile and syntax-check changed modules**

Run: `python -m py_compile app.py domain.py artifacts.py production.py video_bridge.py voice_provider.py; node --check web\\app.js; Push-Location ..\\video_edit_mvp; python -m py_compile creative_engine.py; Pop-Location`

Expected: all commands exit 0.

- [ ] **Step 4: Verify the running server and the interaction**

Run: `Invoke-WebRequest -Uri 'http://127.0.0.1:8092/' -UseBasicParsing | Select-Object -ExpandProperty StatusCode`

Expected: `200`.

In the browser, create or use two harmless test copies, choose `Selecionar todas`, start the batch, and confirm the job reports each card independently. Do not use a real paid voice API for this automated verification; use injected fake providers in tests.
