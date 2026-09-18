# Ofertas por Produto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que uma producao em lote processe copies isoladas por produto/oferta, cada uma com seus takes, B-roll e artefatos proprios.

**Architecture:** Introduzir `Offer` como agregado de copies e caminhos de midia dentro de `HubState`. O servico sempre resolve a oferta ativa para operacoes locais e prepara uma copia de `HubSettings` com os caminhos de uma oferta antes de acionar o motor existente. A producao de lote recebe pares de oferta/copy, preservando cache, concorrencia de voz e isolamento de erro atuais.

**Tech Stack:** Python 3.12, dataclasses, servidor HTTP padrao, JavaScript sem framework, unittest, motor `video_edit_mvp` existente.

**Spec:** `creative_hub/docs/superpowers/specs/2026-09-16-ofertas-por-produto-design.md`

## Global Constraints

- Nunca modificar `C:\FabricaDeVideos`.
- Nunca mover, renomear ou apagar arquivos de midia existentes do usuario.
- Usar nomes e caminhos seguros no Windows.
- Preservar estados legados que possuem somente `settings` e `copies`.
- `Gerar lote` processa todas as ofertas; `Testar selecionado` processa uma unica copy da oferta ativa.
- Nenhum commit e esperado: este workspace nao e um repositorio Git.

---

### Task 1: Modelo de Oferta e Migracao de Estado

**Files:**
- Modify: `creative_hub/domain.py`
- Modify: `creative_hub/storage.py`
- Test: `creative_hub/tests/test_domain.py`
- Test: `creative_hub/tests/test_storage.py`

**Interfaces:**
- Produces `Offer`, `HubState.offers`, `HubState.active_offer_id`, `offer_from_dict`, `offer_to_dict` e `active_offer(state)`.
- Consumes `CopyCard`, `HubSettings` e serializacao existente.

- [ ] **Step 1: Escrever testes de estado legado e isolamento**

```python
def test_legacy_copies_are_migrated_to_default_offer():
    state = state_from_dict({"settings": {}, "copies": [{"id": "a", "title": "Legada"}]})
    assert len(state.offers) == 1
    assert state.active_offer_id == state.offers[0].id
    assert state.offers[0].copies[0].title == "Legada"

def test_offer_state_round_trip_keeps_media_and_copies():
    state = HubState(offers=[Offer(id="kids", name="Kids", slug="kids", takes_folder="C:/takes", copies=[CopyCard(id="a")])], active_offer_id="kids")
    restored = state_from_dict(state_to_dict(state))
    assert restored.offers[0].takes_folder == "C:/takes"
    assert restored.offers[0].copies[0].id == "a"
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

Run: `python -m unittest creative_hub.tests.test_domain creative_hub.tests.test_storage`

Expected: FAIL porque `Offer` e `HubState.offers` ainda nao existem.

- [ ] **Step 3: Implementar dataclasses e serializacao compatvel**

```python
@dataclass
class Offer:
    id: str
    name: str
    slug: str
    takes_folder: str = ""
    broll_path: str = ""
    audio_folder: str = ""
    output_folder: str = ""
    copies: list[CopyCard] = field(default_factory=list)

@dataclass
class HubState:
    settings: HubSettings = field(default_factory=HubSettings)
    offers: list[Offer] = field(default_factory=list)
    active_offer_id: str = ""
```

Quando `offers` estiver ausente, construir uma oferta `Oferta inicial` com os caminhos de `HubSettings` e as copies antigas. `state_to_dict` deve gravar `offers` e `active_offer_id`; `public_state` nao deve expor secrets.

- [ ] **Step 4: Rodar os testes focados**

Run: `python -m unittest creative_hub.tests.test_domain creative_hub.tests.test_storage`

Expected: PASS.

### Task 2: Diretorios e Servico de Ofertas

**Files:**
- Create: `creative_hub/offers.py`
- Modify: `creative_hub/domain.py`
- Modify: `creative_hub/app.py`
- Test: `creative_hub/tests/test_offers.py`
- Test: `creative_hub/tests/test_app_api.py`

**Interfaces:**
- Produces `offer_paths(root, slug)`, `ensure_offer_directories(root, offer)` e `unique_offer_slug(name, existing_slugs)`.
- Produces servico `create_offer`, `update_offer`, `activate_offer`, `delete_offer` e `update_active_offer_media`.
- Consumes `Offer` criado na Task 1.

- [ ] **Step 1: Escrever testes para paths e API**

```python
def test_offer_directories_are_created_without_touching_existing_media(tmp_path):
    offer = Offer(id="kids", name="Kids", slug="kids")
    paths = ensure_offer_directories(tmp_path, offer)
    assert paths.takes_folder == tmp_path / "ofertas" / "kids" / "takes"
    assert paths.output_folder.is_dir()

def test_create_offer_sets_it_as_active(client):
    response = client.post_json("/api/offers", {"name": "Musicais"})
    state = client.get_json("/api/state")
    assert response.status == 201
    assert state["active_offer_id"] == response.body["offer"]["id"]
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

Run: `python -m unittest creative_hub.tests.test_offers creative_hub.tests.test_app_api`

Expected: FAIL porque os helpers e rotas ainda nao existem.

- [ ] **Step 3: Implementar estrutura e rotas**

Criar os diretorios somente dentro de `creative_root/offers/<slug>`. Adicionar a `HubSettings` global `creative_root_folder` como pasta central configuravel. Implementar:

```text
POST /api/offers
PUT /api/offers/<id>
POST /api/offers/<id>/activate
DELETE /api/offers/<id>
PUT /api/offers/<id>/media
```

Impedir apagar oferta com copies e impedir deixar o estado sem uma oferta. Ao criar, usar pasta central caso configurada; sem ela, criar a oferta sem paths e permitir configuracao manual.

- [ ] **Step 4: Rodar os testes focados**

Run: `python -m unittest creative_hub.tests.test_offers creative_hub.tests.test_app_api`

Expected: PASS.

### Task 3: Copies e Configuracao por Oferta Ativa

**Files:**
- Modify: `creative_hub/app.py`
- Modify: `creative_hub/video_bridge.py`
- Test: `creative_hub/tests/test_app_api.py`
- Test: `creative_hub/tests/test_video_bridge.py`

**Interfaces:**
- Produces `_active_offer()` no `HubService` e `settings_for_offer(settings, offer)` no bridge.
- Consumes `Offer` e suas copies/caminhos.

- [ ] **Step 1: Escrever testes para mutacoes locais**

```python
def test_copy_mutations_only_change_active_offer(service):
    first = service.create_offer({"name": "A"})
    service.create_copy({"title": "Copy A"})
    second = service.create_offer({"name": "B"})
    service.create_copy({"title": "Copy B"})
    assert [copy.title for copy in service.state.offers[0].copies] == ["Copy A"]
    assert [copy.title for copy in service.state.offers[1].copies] == ["Copy B"]

def test_settings_for_offer_overrides_only_media_paths():
    resolved = settings_for_offer(HubSettings(subtitle_font_size=24), Offer(id="a", name="A", slug="a", takes_folder="T", broll_path="B", output_folder="O"))
    assert (resolved.takes_folder, resolved.broll_path, resolved.output_folder) == ("T", "B", "O")
    assert resolved.subtitle_font_size == 24
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m unittest creative_hub.tests.test_app_api creative_hub.tests.test_video_bridge`

Expected: FAIL porque copies ainda usam `state.copies` e o bridge nao recebe oferta.

- [ ] **Step 3: Migrar operacoes locais para a oferta ativa**

Atualizar criar, editar, duplicar, apagar e anexar audio para buscar copies em `active_offer.copies`. `public_state` deve retornar somente `copies` da oferta ativa por compatibilidade de UI e tambem retornar `offers`, `active_offer_id` e `active_offer` completos. Resolver `HubSettings` por oferta apenas no momento da renderizacao.

- [ ] **Step 4: Rodar os testes focados**

Run: `python -m unittest creative_hub.tests.test_app_api creative_hub.tests.test_video_bridge`

Expected: PASS.

### Task 4: Producao Multi-Oferta e Cache Isolado

**Files:**
- Modify: `creative_hub/production.py`
- Modify: `creative_hub/artifacts.py`
- Modify: `creative_hub/app.py`
- Test: `creative_hub/tests/test_production.py`
- Test: `creative_hub/tests/test_artifacts.py`

**Interfaces:**
- Produces `ProductionItem(offer, card)` e `ProductionCoordinator.run(items, settings, mode, progress)`.
- Consumes `settings_for_offer` da Task 3.

- [ ] **Step 1: Escrever teste para lote cruzando ofertas**

```python
def test_batch_renders_items_with_their_own_offer_paths(tmp_path):
    items = [ProductionItem(offer_a, CopyCard(id="a", title="A", text="texto")), ProductionItem(offer_b, CopyCard(id="b", title="B", text="texto"))]
    coordinator.run(items, HubSettings(), "batch", lambda *_: None)
    assert render_calls[0].settings.output_folder == offer_a.output_folder
    assert render_calls[1].settings.output_folder == offer_b.output_folder
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m unittest creative_hub.tests.test_production creative_hub.tests.test_artifacts`

Expected: FAIL porque o coordenador recebe somente cards e uma configuracao global.

- [ ] **Step 3: Implementar itens de producao e erros isolados**

No lote, construir um item para cada copy preenchida de cada oferta. Para teste, construir um unico item da oferta ativa. Passar configuracao resolvida por oferta para assinatura, audio, transcricao e renderizacao. Incluir `offer_id` e `offer_name` no resultado de cada item. Validar takes e output por item, capturar erro local e continuar o lote.

- [ ] **Step 4: Rodar os testes focados**

Run: `python -m unittest creative_hub.tests.test_production creative_hub.tests.test_artifacts`

Expected: PASS.

### Task 5: Navegacao de Ofertas e Tela de Midia

**Files:**
- Modify: `creative_hub/web/index.html`
- Modify: `creative_hub/web/app.js`
- Modify: `creative_hub/web/styles.css`
- Test: `creative_hub/tests/test_web_ui.py`

**Interfaces:**
- Consumes `offers`, `active_offer_id`, `active_offer` e rotas da Task 2.
- Produces seletor de oferta ativo, criacao/renomeacao e campos de midia por oferta.

- [ ] **Step 1: Escrever testes estaticos da UI**

```python
def test_web_ui_exposes_offer_workspace_controls():
    source = WEB_APP.read_text(encoding="utf-8")
    assert "createOffer" in source
    assert "activateOffer" in source
    assert "/api/offers" in source
    assert "active_offer" in source
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m unittest creative_hub.tests.test_web_ui`

Expected: FAIL porque a UI ainda nao tem controles de oferta.

- [ ] **Step 3: Implementar UI contida e responsiva**

Adicionar uma faixa de workspace acima das copies com nome da oferta, seletor e botao iconico para criar. A tela Edicao deve separar `Midia desta oferta` dos ajustes globais, com campos para takes, B-roll, audio e output. Ao trocar de oferta, limpar selecao de cards e recarregar as copies ativas. `Gerar lote` continua global e exibe progresso contendo o nome da oferta; `Testar selecionado` continua local.

- [ ] **Step 4: Rodar testes da UI e verificacao de sintaxe**

Run: `python -m unittest creative_hub.tests.test_web_ui`

Run: `node --check creative_hub/web/app.js`

Expected: PASS.

### Task 6: Verificacao Integrada

**Files:**
- Modify: `creative_hub/README.md`
- Test: suites existentes

**Interfaces:**
- Consumes todos os componentes das Tasks 1-5.

- [ ] **Step 1: Documentar o fluxo de ofertas**

Adicionar ao README: como definir a pasta central, criar uma oferta, vincular midia e executar teste/lote.

- [ ] **Step 2: Rodar toda a verificacao**

Run:

```powershell
Push-Location creative_hub
python -m unittest discover -s tests
python -m py_compile app.py domain.py offers.py production.py video_bridge.py artifacts.py
node --check web\app.js
Pop-Location
Push-Location video_edit_mvp
python -m unittest discover -s tests
Pop-Location
```

Expected: todas as suites passam e nao ha erro de sintaxe.

- [ ] **Step 3: Fazer validacao visual local**

Abrir `http://127.0.0.1:8092/`, criar duas ofertas sem midia real, alternar entre elas e verificar que cada uma conserva suas copies. Nao iniciar geracao de voz ou renderizacao real durante a validacao visual.
