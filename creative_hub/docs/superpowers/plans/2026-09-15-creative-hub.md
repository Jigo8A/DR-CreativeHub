# Creative Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone local hub that organizes copy cards, persists creative settings, accepts manual audio, and renders selected Meta Ads creatives using the existing isolated MVP engine.

**Architecture:** `creative_hub` is a small Python HTTP application with a vanilla web frontend. Its domain modules own state, validation and the bridge to `../video_edit_mvp`; the HTTP layer owns routing and job lifecycle only. A provider interface isolates future text-to-speech APIs from the current manual-audio workflow.

**Tech Stack:** Python 3 standard library, existing `video_edit_mvp` Python modules, vanilla HTML/CSS/JavaScript, `unittest`.

**Spec:** `creative_hub/docs/superpowers/specs/2026-09-15-creative-hub-design.md`

## Global Constraints

- Create and edit files only under `creative_hub`; do not modify `C:\FabricaDeVideos` or `video_edit_mvp`.
- Store local hub data in `creative_hub/data/state.json`; never delete, move or rename user input media.
- Reuse `creative_engine.process_creative_batch` and `SubtitleSettings` from the MVP through a bridge module.
- The initial provider surface must not issue real voice API calls before the user supplies provider documentation and credentials.
- Render output is written only to the configured output directory.
- Keep the UI desktop-friendly with a fixed sidebar, clear whitespace, and a faithful 9:16 subtitle preview.
- Run `python -m unittest discover -s tests -v` from `creative_hub` after every backend task.

---

## File Structure

- `creative_hub/app.py`: HTTP server, static file serving, job lifecycle and endpoint dispatch.
- `creative_hub/domain.py`: immutable copy/config models, default state and JSON conversions.
- `creative_hub/storage.py`: atomic local state persistence and state validation boundary.
- `creative_hub/video_bridge.py`: validates selected cards and invokes the existing batch creative engine.
- `creative_hub/voice_provider.py`: text-to-speech provider contract and the intentionally unavailable placeholder provider.
- `creative_hub/modern_folder_picker.py`: copied independent native Windows folder picker implementation; this avoids importing app state from the MVP.
- `creative_hub/web/index.html`: application shell and view templates.
- `creative_hub/web/app.js`: state loading, API calls and browser interactions.
- `creative_hub/web/styles.css`: design tokens, desktop layout and responsive layout.
- `creative_hub/tests/*.py`: unit and HTTP behavior tests.

## Task 1: Domain model and durable state

**Files:**
- Create: `creative_hub/domain.py`
- Create: `creative_hub/storage.py`
- Create: `creative_hub/tests/test_storage.py`
- Create: `creative_hub/tests/__init__.py`

**Interfaces:**
- Produces: `CopyCard`, `HubSettings`, `HubState`, `default_state()`, `state_from_dict(data)`, `state_to_dict(state)`.
- Produces: `StateStore(path).load() -> HubState` and `StateStore(path).save(state: HubState) -> None`.

- [ ] **Step 1: Write the failing state round-trip test**

```python
from pathlib import Path

from domain import CopyCard, default_state
from storage import StateStore


def test_store_round_trips_copy_and_settings(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    state = default_state()
    state.copies.append(CopyCard(id="copy-a", title="Gancho", text="Texto da copy"))
    state.settings.output_folder = r"C:\saida"

    store.save(state)
    restored = store.load()

    assert restored.copies[0].title == "Gancho"
    assert restored.settings.output_folder == r"C:\saida"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_storage -v`

Expected: FAIL because `domain` and `storage` do not exist.

- [ ] **Step 3: Implement focused domain models and atomic storage**

```python
@dataclass
class CopyCard:
    id: str
    title: str = ""
    text: str = ""
    audio_source: str = "api"
    audio_path: str | None = None
    status: str = "draft"
    output_path: str | None = None
    error: str | None = None


class StateStore:
    def save(self, state: HubState) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state_to_dict(state), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
```

`HubSettings` must contain the complete MVP creative configuration plus `voice_provider`, `voice_name` and a write-only `voice_api_key` field. `state_from_dict` must accept missing keys and use defaults so future schema additions do not break older state files.

- [ ] **Step 4: Run the state tests to verify they pass**

Run: `python -m unittest tests.test_storage -v`

Expected: PASS.

- [ ] **Step 5: Commit the isolated domain layer**

Run when Git is initialized: `git add creative_hub/domain.py creative_hub/storage.py creative_hub/tests && git commit -m "feat: add Creative Hub state models"`

## Task 2: Manual audio and video-engine bridge

**Files:**
- Create: `creative_hub/video_bridge.py`
- Create: `creative_hub/voice_provider.py`
- Create: `creative_hub/tests/test_video_bridge.py`

**Interfaces:**
- Consumes: `HubSettings`, `CopyCard` from `domain.py`.
- Produces: `VoiceProvider.generate(card: CopyCard, settings: HubSettings) -> Path`.
- Produces: `UnavailableVoiceProvider.generate(...) -> Path` raising `VoiceProviderUnavailable`.
- Produces: `render_cards(cards, settings, test_only, process_func) -> list[RenderResult]`.

- [ ] **Step 1: Write the failing bridge test with an injected renderer**

```python
from pathlib import Path

from domain import CopyCard, default_state
from video_bridge import render_cards


def test_render_cards_stages_only_selected_manual_audio(tmp_path: Path):
    audio = tmp_path / "copy.wav"
    audio.write_bytes(b"audio")
    card = CopyCard(id="c1", text="Copy", audio_source="manual", audio_path=str(audio), status="audio_ready")
    settings = default_state().settings
    settings.output_folder = str(tmp_path / "output")

    captured = {}
    def fake_process(**kwargs):
        captured.update(kwargs)
        return type("Batch", (), {"items": [], "total": 1, "completed": 1, "failed": 0})()

    render_cards([card], settings, test_only=True, process_func=fake_process)

    assert Path(captured["audio_folder"]).exists()
    assert Path(captured["audio_folder"]).glob("*.wav")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_video_bridge -v`

Expected: FAIL because `video_bridge` does not exist.

- [ ] **Step 3: Implement the future-proof bridge and provider contract**

```python
class VoiceProviderUnavailable(RuntimeError):
    pass


class UnavailableVoiceProvider:
    def generate(self, card: CopyCard, settings: HubSettings) -> Path:
        raise VoiceProviderUnavailable("A API de voz ainda nao foi configurada.")


def render_cards(cards, settings, test_only, process_func=process_creative_batch):
    ready_cards = [card for card in cards if card.audio_path]
    if not ready_cards:
        raise ValueError("Nenhum card selecionado possui audio pronto.")
    # Stage links/copies in a job-local input folder, then call process_func once.
```

Add the MVP parent directory to `sys.path` inside this bridge only. Construct `SubtitleSettings` and `AudioEditSettings` from `HubSettings`, stage only the selected audio paths in a job-local folder under the output directory, call the injected/default engine once, then map engine result items back to cards in original selected order.

- [ ] **Step 4: Add failing tests for unavailable API audio and invalid selected audio**

```python
def test_unavailable_voice_provider_explains_missing_connector():
    with self.assertRaisesRegex(VoiceProviderUnavailable, "API de voz"):
        UnavailableVoiceProvider().generate(CopyCard(id="c", text="Oi"), default_state().settings)
```

Run: `python -m unittest tests.test_video_bridge -v`

Expected: FAIL until the provider behavior is implemented.

- [ ] **Step 5: Implement validation and verify all bridge tests**

Run: `python -m unittest tests.test_video_bridge -v`

Expected: PASS.

- [ ] **Step 6: Commit the engine boundary**

Run when Git is initialized: `git add creative_hub/video_bridge.py creative_hub/voice_provider.py creative_hub/tests/test_video_bridge.py && git commit -m "feat: bridge copy cards to video engine"`

## Task 3: Local HTTP API and render job lifecycle

**Files:**
- Create: `creative_hub/app.py`
- Create: `creative_hub/modern_folder_picker.py`
- Create: `creative_hub/tests/test_app_api.py`
- Create: `creative_hub/web/index.html`
- Create: `creative_hub/web/app.js`
- Create: `creative_hub/web/styles.css`

**Interfaces:**
- Consumes: `StateStore`, `render_cards`, `UnavailableVoiceProvider`.
- Produces: HTTP APIs listed in the design specification and `GET /api/job` payload `{running, status, progress, results, error}`.

- [ ] **Step 1: Write the failing HTTP API tests**

```python
def test_create_copy_persists_and_returns_card(server_client):
    response = server_client.post_json("/api/copies", {"title": "Nova", "text": "Uma copy"})
    assert response.status == 201
    created = response.json["copy"]
    assert created["title"] == "Nova"
    assert server_client.get_json("/api/state")["copies"][0]["id"] == created["id"]


def test_api_generation_without_provider_returns_clear_error(server_client):
    response = server_client.post_json("/api/voice/generate", {"copy_ids": ["copy-a"]})
    assert response.status == 422
    assert "API de voz" in response.json["error"]
```

- [ ] **Step 2: Run the endpoint tests to verify they fail**

Run: `python -m unittest tests.test_app_api -v`

Expected: FAIL because `app` and the HTTP routes do not exist.

- [ ] **Step 3: Implement thin HTTP routing around the domain modules**

```python
def do_POST(self):
    path = request_path(self.path)
    payload = read_json(self)
    if path == "/api/copies":
        copy = service.create_copy(payload)
        return json_response(self, {"copy": copy_to_dict(copy)}, 201)
    if path == "/api/render/batch":
        return service.start_render(payload, test_only=False)
```

Copy the proven independent `IFileOpenDialog` picker into `creative_hub/modern_folder_picker.py`, keeping it separate from the MVP. The service layer must lock a single active render job, start a background thread, and report per-card progress/results. `POST /api/copies/:id/audio` accepts a local path string and validates it is an existing audio file. Static files are served only from `web/`, and `/api/video` may only read a file returned by a completed job.

- [ ] **Step 4: Add a failing test for persisted settings and test-only rendering**

```python
def test_settings_persist_and_test_render_selects_one_card(server_client):
    server_client.put_json("/api/settings", {"subtitle_font_size": 34, "output_folder": r"C:\renders"})
    assert server_client.get_json("/api/state")["settings"]["subtitle_font_size"] == 34
    response = server_client.post_json("/api/render/test", {"copy_ids": ["a", "b"]})
    assert response.status == 202
```

- [ ] **Step 5: Implement the job and settings behavior, then run all backend tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS.

- [ ] **Step 6: Commit the HTTP application**

Run when Git is initialized: `git add creative_hub/app.py creative_hub/modern_folder_picker.py creative_hub/web creative_hub/tests/test_app_api.py && git commit -m "feat: add Creative Hub local API"`

## Task 4: Organized creative-workspace interface

**Files:**
- Modify: `creative_hub/web/index.html`
- Modify: `creative_hub/web/app.js`
- Modify: `creative_hub/web/styles.css`
- Create: `creative_hub/tests/test_web_ui.py`

**Interfaces:**
- Consumes: `GET /api/state`, copy CRUD APIs, settings API, render APIs and job API.
- Produces: `renderCreativeView(state)`, `renderEditView(state)`, `renderSettingsView(state)`, `saveSettings()` and `renderJobStatus(job)`.

- [ ] **Step 1: Write failing source-level UI coverage**

```python
def test_ui_has_three_primary_workspace_views():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="creative"' in html
    assert 'data-view="edit"' in html
    assert 'data-view="settings"' in html


def test_ui_has_vertical_subtitle_preview_and_render_actions():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "creativeSubtitlePreview" in script
    assert "/api/render/test" in script
    assert "/api/render/batch" in script
```

- [ ] **Step 2: Run the UI test to verify it fails**

Run: `python -m unittest tests.test_web_ui -v`

Expected: FAIL because the page shell does not contain the required workspace controls.

- [ ] **Step 3: Implement the complete app shell and views**

```html
<aside class="sidebar">
  <button class="nav-item active" data-view="creative">Criativos</button>
  <button class="nav-item" data-view="edit">Edicao</button>
  <button class="nav-item" data-view="settings">Configuracoes</button>
</aside>
<main class="workspace">
  <section id="creativeView" class="view active"></section>
  <section id="editView" class="view"></section>
  <section id="settingsView" class="view"></section>
</main>
```

Implement cards as a single-level vertical list with selection checkbox, title/text fields, source selector, audio attachment path, status, media actions and compact icon buttons for duplicate/delete. Build the editing screen in two columns: configuration form and a 9:16 preview. Preview text must be draggable, resizable with a visible handle, and mapped to normalized subtitle X/Y and font size values. Persist edits after a short debounce and show a saved state in the top bar.

- [ ] **Step 4: Add UI assertions for cards and subtitle controls**

```python
def test_ui_exposes_card_status_audio_source_and_caption_controls():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for token in ["audio_source", "status", "subtitle_x_position", "subtitle_y_position", "subtitle_font_size"]:
        assert token in script
```

- [ ] **Step 5: Implement interactions and verify UI tests**

Run: `python -m unittest tests.test_web_ui -v`

Expected: PASS.

- [ ] **Step 6: Commit the workspace UI**

Run when Git is initialized: `git add creative_hub/web creative_hub/tests/test_web_ui.py && git commit -m "feat: add Creative Hub workspace UI"`

## Task 5: End-to-end verification and handoff

**Files:**
- Create: `creative_hub/README.md`
- Modify: `creative_hub/tests/test_app_api.py`

**Interfaces:**
- Consumes: all application modules and documented startup command.
- Produces: repeatable local startup and a verified manual-audio creative render workflow.

- [ ] **Step 1: Write the failing test for protected API-key state output**

```python
def test_state_endpoint_never_returns_saved_voice_api_key(server_client):
    server_client.put_json("/api/settings", {"voice_api_key": "private-key"})
    settings = server_client.get_json("/api/state")["settings"]
    assert settings["voice_api_key"] == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_app_api.test_state_endpoint_never_returns_saved_voice_api_key -v`

Expected: FAIL until API serialization removes the secret.

- [ ] **Step 3: Implement secret masking and README instructions**

```python
def public_settings(settings: HubSettings) -> dict:
    payload = settings_to_dict(settings)
    payload["voice_api_key"] = ""
    return payload
```

Document the local URL, startup command, manual audio workflow, required MVP dependency, output safety, and the current API-voice limitation. Do not document an unimplemented provider as usable.

- [ ] **Step 4: Run all automated checks**

Run: `python -m unittest discover -s tests -v`

Run: `python -m py_compile app.py domain.py storage.py video_bridge.py voice_provider.py modern_folder_picker.py`

Expected: PASS for both commands.

- [ ] **Step 5: Start the local app and perform visual QA**

Run: `python app.py`

Verify in the browser at the configured port:

- `Criativos`, `Edicao` and `Configuracoes` navigate without a page reload.
- A card can be created, edited, duplicated and removed.
- The 9:16 preview drag and resize controls update visible position and size.
- Folder picker buttons exist in every folder input group.
- Main render actions remain visible without traversing the entire page.
- Desktop and a 390px-wide viewport have no horizontal overflow or clipped primary controls.

- [ ] **Step 6: Commit verified documentation and safety behavior**

Run when Git is initialized: `git add creative_hub/README.md creative_hub/tests/test_app_api.py creative_hub/app.py && git commit -m "docs: document Creative Hub workflow"`

