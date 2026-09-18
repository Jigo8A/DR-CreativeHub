# Distribuicao do Creative Hub pelo GitHub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empacotar o Creative Hub e seu motor de renderizacao para instalacao repetivel em Windows a partir de um repositorio privado.

**Architecture:** Um repositorio raiz passa a conter `creative_hub` e `video_edit_mvp` lado a lado. O Hub resolve o motor por esse layout, enquanto scripts PowerShell verificam pre-requisitos, instalam dependencias e iniciam o servidor. Estado, segredos, midias e artefatos permanecem locais por meio de `.gitignore`.

**Tech Stack:** Python 3.12+, PowerShell 5.1+, Node.js/npm, Vite, FFmpeg, faster-whisper, GitHub CLI/Git.

**Spec:** `docs/superpowers/specs/2026-09-18-distribuicao-github-design.md`

## Global Constraints

- O repositorio GitHub sera privado e se chamara `DR-CreativeHub`.
- Nenhum arquivo de estado, chave de API, caminho pessoal, midia de oferta, output, log ou cache entra no Git.
- O Hub nao pode depender de `C:\\FabricaDeVideos` ou outro caminho pessoal.
- O instalador nao instala silenciosamente programas de sistema nem altera configuracoes globais do Windows.
- FFmpeg e um pre-requisito externo; o diagnostico deve indicar sua ausencia claramente.
- O estado inicial de cada clone deve estar vazio e ser criado localmente na primeira abertura.

---

### Task 1: Tornar a resolucao do motor portatil

**Files:**
- Modify: `creative_hub/video_bridge.py:17-28`
- Create: `creative_hub/tests/test_distribution_layout.py`
- Modify: `creative_hub/README.md`

**Interfaces:**
- Produces: `resolve_mvp_root(hub_root: Path | None = None) -> Path`.
- Produces: `MVP_ROOT` como `<repository-root>/video_edit_mvp`.

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_mvp_root_uses_repository_sibling() -> None:
    hub_root = Path(r"C:\\repo\\creative_hub")
    assert resolve_mvp_root(hub_root) == Path(r"C:\\repo\\video_edit_mvp")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_distribution_layout.DistributionLayoutTests.test_resolve_mvp_root_uses_repository_sibling`

Expected: FAIL because `resolve_mvp_root` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def resolve_mvp_root(hub_root: Path | None = None) -> Path:
    root = hub_root or Path(__file__).resolve().parent
    return root.parent / "video_edit_mvp"
```

Assign `MVP_ROOT = resolve_mvp_root()` before importing engine modules and update the README with the portable layout.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_distribution_layout.DistributionLayoutTests.test_resolve_mvp_root_uses_repository_sibling`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add creative_hub/video_bridge.py creative_hub/tests/test_distribution_layout.py creative_hub/README.md
git commit -m "feat: resolve bundled video engine portably"
```

### Task 2: Montar a arvore limpa de distribuicao

**Files:**
- Create: `DR-CreativeHub/creative_hub/` copied from the prepared source tree.
- Create: `DR-CreativeHub/video_edit_mvp/` copied from the prepared engine tree.

**Interfaces:**
- Produces: a clean repository root containing only runtime source, tests, assets, manifests, scripts, and documentation.
- Consumes: prepared source directories without state, API keys, outputs, logs, caches, or development media.

- [ ] **Step 1: Create the allowed-file manifest**

Allow Python source, web source and build output, normal application fonts, tests, docs, `package.json`, `package-lock.json`, and engine requirements. Exclude `data/state.json`, `node_modules`, `__pycache__`, `.venv`, logs, outputs, temp directories, caches, screenshots, and manual media.

- [ ] **Step 2: Copy into a new distribution root**

Run PowerShell copy operations that target the new `DR-CreativeHub` directory only. Do not move, delete, or alter either development source directory.

- [ ] **Step 3: Verify the copy is complete and clean**

Run: `rg --files DR-CreativeHub` and inspect the excluded-pattern scan.

Expected: both `creative_hub` and `video_edit_mvp` contain their source and tests; no prohibited local artifacts are present.

- [ ] **Step 4: Commit**

```powershell
git add creative_hub video_edit_mvp
git commit -m "chore: bundle Creative Hub and video engine"
```

### Task 3: Criar diagnostico e instalacao Windows

**Files:**
- Create: `scripts/diagnostico.ps1`
- Create: `scripts/install.ps1`
- Create: `scripts/abrir-hub.ps1`
- Create: `creative_hub/tests/test_distribution_scripts.py`

**Interfaces:**
- Produces: `Test-CreativeHubPrerequisites` with `Name`, `Ready`, and `Message`.
- Produces: installation that creates `.venv`, installs Python dependencies, runs `npm ci`, and runs `npm run build`.
- Produces: launcher that starts `creative_hub/app.py` and opens `http://127.0.0.1:8092`.

- [ ] **Step 1: Write the failing test**

```python
def test_distribution_scripts_exist_without_personal_paths() -> None:
    for name in ("diagnostico.ps1", "install.ps1", "abrir-hub.ps1"):
        content = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "FabricaDeVideos" not in content
        assert "PCGamerInfor" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest creative_hub.tests.test_distribution_scripts.DistributionScriptTests.test_distribution_scripts_exist_without_personal_paths`

Expected: FAIL because the scripts do not exist.

- [ ] **Step 3: Write minimal implementation**

`diagnostico.ps1` uses `Get-Command` to check `python`, `node`, `npm`, and `ffmpeg`, then returns nonzero if a prerequisite is missing. `install.ps1` dot-sources the diagnostic, creates `.venv`, runs `.venv\\Scripts\\python.exe -m pip install -r requirements.txt`, then runs `npm ci` and `npm run build` in `creative_hub/headline_studio`. `abrir-hub.ps1` resolves the root with `$PSScriptRoot`, verifies the venv, starts the app from its own folder, then uses `Start-Process` for localhost.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest creative_hub.tests.test_distribution_scripts`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts creative_hub/tests/test_distribution_scripts.py
git commit -m "feat: add Windows installation and diagnostics scripts"
```

### Task 4: Preparar indice Git e estado limpo

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `creative_hub/data/.gitkeep`
- Create: `creative_hub/tests/test_distribution_files.py`

**Interfaces:**
- Produces: clone starts without `creative_hub/data/state.json`; `StateStore.load()` creates the default state in memory and first save creates the local file.
- Produces: root requirements pin `faster-whisper==1.2.1`.

- [ ] **Step 1: Write the failing test**

```python
def test_gitignore_excludes_state_and_generated_content() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in ("creative_hub/data/state.json", "**/node_modules/", "*.log", "__pycache__/", "*.mp4", ".venv/"):
        assert rule in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest creative_hub.tests.test_distribution_files.DistributionFileTests`

Expected: FAIL because root packaging files do not exist.

- [ ] **Step 3: Write minimal implementation**

Add the root requirements and ignore rules for state, credentials, media, outputs, logs, caches, `node_modules`, virtual environments, test artifacts, and generated emoji previews. Add only `creative_hub/data/.gitkeep`; do not add the current state, output, or cache files. Keep source code, tests, package lock files, and required normal fonts tracked.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest creative_hub.tests.test_distribution_files.DistributionFileTests`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore requirements.txt creative_hub/data/.gitkeep creative_hub/tests/test_distribution_files.py
git commit -m "chore: prepare clean distributable workspace"
```

### Task 5: Documentar e validar distribuicao limpa

**Files:**
- Create: `README.md`
- Modify: `creative_hub/README.md`
- Modify: `creative_hub/tests/test_distribution_scripts.py`

**Interfaces:**
- Produces: README with clone, PowerShell installation, launch, FFmpeg guidance, and per-user OpenSpeaker/AssemblyAI setup.

- [ ] **Step 1: Write the failing test**

```python
def test_root_readme_documents_installation_flow() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in ("install.ps1", "abrir-hub.ps1", "FFmpeg", "OpenSpeaker", "AssemblyAI"):
        assert text in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest creative_hub.tests.test_distribution_scripts.DistributionScriptTests.test_root_readme_documents_installation_flow`

Expected: FAIL because the root README does not exist.

- [ ] **Step 3: Write minimal implementation**

Document this exact flow:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
.\scripts\abrir-hub.ps1
```

Explain that each person supplies their own API keys and media folders, and that access is granted through a private GitHub invitation.

- [ ] **Step 4: Run clean validation**

```powershell
python -m unittest discover -s creative_hub/tests
Push-Location creative_hub/headline_studio
npm ci
npm run build
Pop-Location
git status --short
```

Expected: Python tests and the web build pass; no state, keys, media, logs, caches, or `node_modules` are staged.

- [ ] **Step 5: Commit**

```powershell
git add README.md creative_hub/README.md creative_hub/tests/test_distribution_scripts.py
git commit -m "docs: document private Creative Hub installation"
```

### Task 6: Criar e publicar o repositorio privado

**Files:**
- Modify: `.gitignore` only if final secret scan finds an uncovered generated path.

**Interfaces:**
- Produces: private GitHub repository `DR-CreativeHub` with source, tests, embedded engine, scripts and docs.

- [ ] **Step 1: Inspect the final index for prohibited content**

```powershell
git status --short
git grep -n -I -E 'sk_[A-Za-z0-9_-]{12,}|api[_-]?key[[:space:]]*[:=]' -- .
```

Expected: no real API key and no state or media content in tracked files.

- [ ] **Step 2: Initialize and commit**

```powershell
git init
git add .
git commit -m "Initial private Creative Hub distribution"
```

Expected: source, tests, scripts, docs, and embedded engine are committed; ignored local data is absent.

- [ ] **Step 3: Create private repository and push**

```powershell
gh repo create DR-CreativeHub --private --source . --remote origin --push
```

Expected: GitHub returns the private repository URL and `origin` points to it.

- [ ] **Step 4: Verify remote**

```powershell
gh repo view --json name,isPrivate,url
git status --short
```

Expected: `isPrivate` is `true` and no prohibited local data appears in the working tree.

- [ ] **Step 5: Give friend onboarding prompt**

```text
Clone this private repository, read README.md, run the documented Windows installation flow, and stop to report any missing prerequisite without modifying global Windows settings.
```
