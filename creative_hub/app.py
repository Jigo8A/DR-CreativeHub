from __future__ import annotations

import json
import mimetypes
import os
import shutil
import threading
import traceback
import uuid
from dataclasses import asdict, replace
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from artifacts import ArtifactPlan
from batches import build_batch_targets
from domain import CopyCard, HubSettings, HubState, Offer, copy_to_dict, offer_to_dict, settings_to_dict, state_to_dict
from font_catalog import FONT_DIR, FONT_SUFFIXES, discover_font_names
from manual_audio import AUDIO_SUFFIXES, ManualImportResult, import_manual_audio, rollback_manual_audio_import
from music_library import MUSIC_ROOT, scan_music_library
from modern_folder_picker import pick_file, pick_folder, pick_font
from offers import ensure_offer_directories, unique_offer_slug
from production import ProductionCoordinator, ProductionItem, is_production_eligible
from storage import StateStore
from video_bridge import render_cards, render_headline_preview, settings_for_offer
from voice_provider import OpenSpeakerVoiceProvider, VoiceProviderError, VoiceProviderUnavailable


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
PORT = 8092
class HubService:
    def __init__(
        self,
        data_root: Path,
        render_func=render_cards,
        voice_provider_factory=OpenSpeakerVoiceProvider,
        folder_picker=pick_folder,
        file_picker=pick_file,
        font_picker=pick_font,
        folder_opener=os.startfile,
        headline_preview_renderer=render_headline_preview,
        production_coordinator_factory=None,
    ) -> None:
        self.data_root = Path(data_root)
        self.store = StateStore(self.data_root / "data" / "state.json")
        self.state = self.store.load()
        self._restore_managed_audio_folders()
        self.render_func = render_func
        self.voice_provider_factory = voice_provider_factory
        self.folder_picker = folder_picker
        self.file_picker = file_picker
        self.font_picker = font_picker
        self.folder_opener = folder_opener
        self.headline_preview_renderer = headline_preview_renderer
        self.production_coordinator_factory = production_coordinator_factory or (lambda: ProductionCoordinator(self.voice_provider_factory))
        self.lock = threading.Lock()
        self.picker_lock = threading.Lock()
        self.job = {"running": False, "status": "Pronto", "progress": 0, "results": [], "error": None}

    def public_state(self) -> dict:
        with self.lock:
            payload = state_to_dict(self.state, include_secret=False)
            payload["copies"] = [copy_to_dict(copy) for copy in self.state.copies]
            payload["active_offer"] = offer_to_dict(self.state.active_offer)
            payload["available_fonts"] = discover_font_names()
            payload["music_library"] = {
                category: [{"name": track.path.name, "path": str(track.path), "category": category} for track in tracks]
                for category, tracks in scan_music_library().items()
            }
            return payload

    def create_offer(self, payload: dict) -> Offer:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Informe o nome da oferta.")
        with self.lock:
            slug = unique_offer_slug(name, {offer.slug for offer in self.state.offers})
            offer = Offer(id=uuid.uuid4().hex, name=name, slug=slug)
            root = self.state.settings.creative_root_folder.strip()
            if root:
                offer = ensure_offer_directories(Path(root), offer)
            self.state.offers.append(offer)
            self.state.active_offer_id = offer.id
            self._save()
            return offer

    def activate_offer(self, offer_id: str) -> Offer:
        with self.lock:
            offer = self._find_offer(offer_id)
            self.state.active_offer_id = offer.id
            self._save()
            return offer

    def delete_offer(self, offer_id: str) -> None:
        with self.lock:
            if self.job["running"]:
                raise RuntimeError("Aguarde o processamento atual terminar antes de excluir uma oferta.")
            if len(self.state.offers) <= 1:
                raise ValueError("Mantenha pelo menos uma oferta no Creative Hub.")
            offer = self._find_offer(offer_id)
            managed_folder = self._managed_offer_folder(offer)
            if managed_folder and managed_folder.exists():
                if managed_folder.is_symlink():
                    raise RuntimeError("A pasta da oferta nao pode ser um atalho ou link simbolico.")
                shutil.rmtree(managed_folder)
            self.state.offers = [item for item in self.state.offers if item.id != offer.id]
            if self.state.active_offer_id == offer.id:
                self.state.active_offer_id = self.state.offers[0].id
            self._save()

    def update_offer(self, offer_id: str, payload: dict) -> Offer:
        with self.lock:
            offer = self._find_offer(offer_id)
            if "name" in payload:
                name = str(payload["name"]).strip()
                if not name:
                    raise ValueError("Informe o nome da oferta.")
                offer.name = name
            for field in (
                "takes_folder",
                "broll_path",
                "manual_audio_inbox_folder",
                "manual_audio_library_folder",
                "output_folder",
                "background_music_mode",
                "background_music_track_path",
                "background_music_category",
            ):
                if field in payload:
                    setattr(offer, field, str(payload[field]).strip())
            api_audio_folder = payload.get("api_audio_folder", payload.get("audio_folder"))
            if api_audio_folder is not None:
                offer.api_audio_folder = str(api_audio_folder).strip()
                offer.audio_folder = offer.api_audio_folder
            self._save()
            return offer

    def create_copy(self, payload: dict) -> CopyCard:
        copy = CopyCard(id=uuid.uuid4().hex, title=str(payload.get("title", "")).strip(), text=str(payload.get("text", "")).strip())
        with self.lock:
            self.state.copies.append(copy)
            self._save()
        return copy

    def update_copy(self, copy_id: str, payload: dict) -> CopyCard:
        with self.lock:
            copy = self._find_copy(copy_id)
            for field in ("title", "text", "audio_source", "voice_name", "background_music_mode", "background_music_track_path", "background_music_category"):
                if field in payload:
                    setattr(copy, field, str(payload[field]).strip())
            if "headline" in payload:
                headline = payload["headline"]
                if headline is not None and not isinstance(headline, dict):
                    raise ValueError("A headline da copy deve ser um objeto ou nula.")
                copy.headline = dict(headline) if headline else None
            self._save()
            return copy

    def duplicate_copy(self, copy_id: str) -> CopyCard:
        with self.lock:
            source = self._find_copy(copy_id)
            duplicate = CopyCard(
                id=uuid.uuid4().hex,
                title=f"{source.title} (copia)".strip(),
                text=source.text,
                audio_source=source.audio_source,
                voice_name=source.voice_name,
                audio_path=source.audio_path,
                status="audio_ready" if source.audio_path else "draft",
                headline=dict(source.headline) if source.headline else None,
            )
            self.state.copies.append(duplicate)
            self._save()
            return duplicate

    def delete_copy(self, copy_id: str) -> None:
        with self.lock:
            offer = self.state.active_offer
            offer.copies = [copy for copy in offer.copies if copy.id != copy_id]
            self._save()

    def attach_audio(self, copy_id: str, audio_path: str) -> CopyCard:
        path = Path(str(audio_path).strip().strip('"'))
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            raise ValueError("Selecione um arquivo de audio valido.")
        with self.lock:
            copy = self._find_copy(copy_id)
            copy.audio_path = str(path)
            copy.audio_source = "manual"
            copy.status = "audio_ready"
            copy.audio_signature = None
            copy.transcript_signature = None
            copy.render_signature = None
            copy.transcript_path = None
            copy.subtitle_path = None
            copy.output_path = None
            copy.error = None
            self._save()
            return copy

    def import_manual_audio(self, offer_id: str | None = None) -> ManualImportResult:
        with self.lock:
            if self.job["running"]:
                raise RuntimeError("Aguarde o processamento atual terminar antes de importar audios manuais.")
            offer = self._find_offer(offer_id) if offer_id else self.state.active_offer
            result = import_manual_audio(offer, datetime.now())
            if result.imported:
                original_count = len(offer.copies)
                offer.copies.extend(result.imported)
                try:
                    self._save()
                except Exception:
                    del offer.copies[original_count:]
                    rollback_manual_audio_import(offer, result)
                    raise
            return result

    def update_settings(self, payload: dict) -> HubSettings:
        with self.lock:
            values = settings_to_dict(self.state.settings)
            for key, value in payload.items():
                if key in values:
                    if key in {"voice_api_key", "assemblyai_api_key"} and not str(value).strip():
                        continue
                    if key == "voice_speed":
                        try:
                            value = float(value)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("A velocidade da narracao deve estar entre 0.50 e 1.50.") from exc
                        if not 0.5 <= value <= 1.5:
                            raise ValueError("A velocidade da narracao deve estar entre 0.50 e 1.50.")
                    if key == "background_music_offset_db":
                        value = float(value)
                        if not -40 <= value <= -4:
                            raise ValueError("A diferenca da musica deve ficar entre -40 e -4 dB.")
                    if key == "render_concurrency":
                        try:
                            value = int(value)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("Escolha 1 ou 2 renderizacoes simultaneas.") from exc
                        if value not in {1, 2}:
                            raise ValueError("Escolha 1 ou 2 renderizacoes simultaneas.")
                    values[key] = value
            self.state.settings = HubSettings(**values)
            self._save()
            return self.state.settings

    def select_folder(self, current_path: str) -> str:
        return self._select_with_lock(self.folder_picker, _initial_folder(current_path))

    def select_file(self, current_path: str) -> str:
        return self._select_with_lock(self.file_picker, _initial_folder(current_path))

    def select_font(self, current_path: str) -> str:
        return self._select_with_lock(self.font_picker, _initial_folder(current_path))

    def import_font(self, source_path: str) -> list[str]:
        source = Path(str(source_path).strip().strip('"'))
        if not source.is_file() or source.suffix.lower() not in FONT_SUFFIXES:
            raise ValueError("Selecione um arquivo de fonte .ttf ou .otf valido.")
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        destination = FONT_DIR / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return discover_font_names()

    def open_offer_folder(self, offer_id: str, field: str) -> None:
        allowed_fields = {
            "takes_folder",
            "broll_path",
            "audio_folder",
            "api_audio_folder",
            "manual_audio_inbox_folder",
            "manual_audio_library_folder",
            "output_folder",
        }
        if field not in allowed_fields:
            raise ValueError("Pasta da oferta invalida.")
        with self.lock:
            offer = self._find_offer(offer_id)
            configured_value = str(getattr(offer, field)).strip().strip('"')
            if not configured_value:
                raise ValueError("Defina esta pasta antes de abri-la.")
            configured_path = Path(configured_value)
            if configured_path.is_dir():
                folder = configured_path
            elif configured_path.is_file() or field == "broll_path":
                folder = configured_path.parent
            else:
                folder = configured_path
            if not folder.is_dir():
                raise ValueError("A pasta configurada nao foi encontrada.")
            self.folder_opener(str(folder))

    def _select_with_lock(self, picker, initial: Path) -> str:
        if not self.picker_lock.acquire(blocking=False):
            raise RuntimeError("Ja existe um seletor de arquivos aberto.")
        try:
            return picker(initial)
        finally:
            self.picker_lock.release()

    def headline_preview(self, payload: dict) -> bytes:
        with self.lock:
            values = settings_to_dict(self.state.settings)
        for key, value in payload.items():
            if key.startswith("headline_") and key in values:
                values[key] = value
        return self.headline_preview_renderer(HubSettings(**values))

    def list_voices(self, provider: str) -> list[dict]:
        provider_name = str(provider).strip().lower()
        if provider_name not in {"clone", "elevenlabs", "minimax", "edge", "kokoro", "vbee", "fishaudio"}:
            raise ValueError("Selecione um provedor de voz valido.")
        with self.lock:
            settings = self.state.settings
            if not settings.voice_api_key.strip():
                raise ValueError("Informe a chave da API OpenSpeaker nas configuracoes.")
        return self.voice_provider_factory().list_voices(settings, provider_name)

    def start_voice_generation(self, copy_ids: list[str]) -> None:
        with self.lock:
            if self.job["running"]:
                raise RuntimeError("Ja existe um processamento em andamento.")
            cards = [card for card in self._selected_cards(copy_ids) if card.audio_source != "manual"]
            if not cards:
                raise ValueError("Selecione pelo menos um criativo configurado para gerar por API.")
            if not self.state.settings.voice_api_key.strip():
                raise ValueError("Informe a chave da API OpenSpeaker nas configuracoes.")
            if not self.state.settings.voice_name.strip():
                raise ValueError("Informe uma voz OpenSpeaker nas configuracoes.")
            offer_settings = settings_for_offer(self.state.settings, self.state.active_offer)
            if not offer_settings.manual_audio_folder.strip():
                raise ValueError("Selecione uma pasta de audios API antes de gerar os audios.")
            if not offer_settings.output_folder.strip():
                raise ValueError("Selecione uma pasta de saida antes de gerar os audios.")
            for card in cards:
                card.status = "generating"
                card.error = None
            self._save()
            self.job = {"running": True, "status": "Preparando narracoes...", "progress": 3, "results": [], "error": None}
        thread = threading.Thread(target=self._run_voice_generation, args=(cards, offer_settings), daemon=True)
        thread.start()

    def start_render(self, copy_ids: list[str], test_only: bool) -> None:
        with self.lock:
            if self.job["running"]:
                raise RuntimeError("Ja existe um processamento em andamento.")
            cards = self._selected_cards(copy_ids)
            if not cards:
                raise ValueError("Selecione pelo menos um criativo.")
            self.job = {"running": True, "status": "Preparando criativos...", "progress": 5, "results": [], "error": None}
        thread = threading.Thread(target=self._run_render, args=(cards, test_only), daemon=True)
        thread.start()

    def start_production(
        self,
        mode: str,
        copy_ids: list[str],
        scope: str = "all",
        batch_mode: str = "automatic",
        batch_names: dict[str, str] | None = None,
    ) -> None:
        with self.lock:
            if self.job["running"]:
                raise RuntimeError("Ja existe um processamento em andamento.")
            batch_targets = None
            if mode == "batch":
                if scope == "all":
                    offers = [offer for offer in self.state.offers if any(is_production_eligible(card) for card in offer.copies)]
                elif scope == "active":
                    offers = [self.state.active_offer] if any(is_production_eligible(card) for card in self.state.active_offer.copies) else []
                else:
                    raise ValueError("Escopo de producao invalido.")
                cards = [ProductionItem(offer, card) for offer in offers for card in offer.copies if is_production_eligible(card)]
                names = batch_names if isinstance(batch_names, dict) else None
                if batch_names is not None and names is None:
                    raise ValueError("Os nomes dos lotes devem ser informados por oferta.")
                batch_targets = build_batch_targets(offers, str(batch_mode).strip().lower(), names or {}, datetime.now())
            elif mode == "test":
                cards = [ProductionItem(self.state.active_offer, card) for card in self._selected_cards(copy_ids)]
                if len(cards) != 1:
                    raise ValueError("Selecione exatamente uma copy para testar.")
            else:
                raise ValueError("Modo de producao invalido.")
            if not cards:
                raise ValueError("Nenhuma copy pronta para producao foi encontrada.")
            self.job = {"running": True, "status": "Preparando producao...", "progress": 1, "results": [], "error": None}
        thread = threading.Thread(target=self._run_production, args=(cards, mode, batch_targets), daemon=True)
        thread.start()

    def job_state(self) -> dict:
        with self.lock:
            return dict(self.job)

    def _run_render(self, cards: list[CopyCard], test_only: bool) -> None:
        try:
            results = self.render_func(cards, settings_for_offer(self.state.settings, self.state.active_offer), test_only)
            with self.lock:
                self._save()
                self.job = {
                    "running": False,
                    "status": "Teste finalizado" if test_only else "Criativos finalizados",
                    "progress": 100,
                    "results": [asdict(item) for item in results],
                    "error": None,
                }
        except Exception as exc:
            with self.lock:
                self.job = {"running": False, "status": "Erro no processamento", "progress": 0, "results": [], "error": str(exc)}

    def _run_voice_generation(self, cards: list[CopyCard], base_settings: HubSettings) -> None:
        provider = self.voice_provider_factory()
        results = []
        total = len(cards)
        for index, card in enumerate(cards, start=1):
            try:
                def update_progress(message: str, progress: int | None) -> None:
                    local_progress = progress if progress is not None else 15
                    overall = min(97, round(((index - 1 + local_progress / 100) / total) * 100))
                    with self.lock:
                        self.job.update({"status": f"Narrando {index}/{total}: {message}", "progress": overall})

                settings = replace(base_settings, voice_name=card.voice_name or base_settings.voice_name)
                plan = ArtifactPlan.from_card(card, settings)
                audio_path = provider.generate(card, settings, progress_callback=update_progress, destination=plan.audio_path)
                card.audio_path = str(audio_path)
                card.audio_signature = plan.audio_signature
                card.audio_source = "api"
                card.status = "audio_ready"
                card.error = None
                results.append({"card_id": card.id, "status": "completed", "audio_path": str(audio_path), "error": None})
            except Exception as exc:
                card.status = "error"
                card.error = str(exc)
                results.append({"card_id": card.id, "status": "failed", "audio_path": None, "error": str(exc)})
        completed = sum(item["status"] == "completed" for item in results)
        with self.lock:
            self._save()
            self.job = {
                "running": False,
                "status": "Narracoes finalizadas" if completed == total else "Narracoes finalizadas com erros",
                "progress": 100,
                "results": results,
                "error": None if completed else "Uma ou mais narracoes falharam.",
            }

    def _run_production(self, cards: list[ProductionItem], mode: str, batch_targets=None) -> None:
        try:
            coordinator = self.production_coordinator_factory()

            def update_progress(status: str, progress: int, results: list[dict]) -> None:
                with self.lock:
                    self.job.update({"status": status, "progress": progress, "results": list(results)})

            results = coordinator.run(cards, self.state.settings, mode, update_progress, batch_targets=batch_targets)
            failed = any(item["status"] != "completed" for item in results)
            with self.lock:
                self._save()
                self.job = {
                    "running": False,
                    "status": "Producao finalizada com erros" if failed else "Producao finalizada",
                    "progress": 100,
                    "results": results,
                    "error": "Uma ou mais copies falharam." if failed else None,
                }
        except Exception as exc:
            with self.lock:
                self.job = {"running": False, "status": "Erro no processamento", "progress": 0, "results": [], "error": str(exc)}

    def _selected_cards(self, copy_ids: list[str]) -> list[CopyCard]:
        selected_ids = set(str(copy_id) for copy_id in copy_ids)
        return [copy for copy in self.state.copies if copy.id in selected_ids]

    def _find_copy(self, copy_id: str) -> CopyCard:
        for copy in self.state.copies:
            if copy.id == copy_id:
                return copy
        raise ValueError("Criativo nao encontrado.")

    def _find_offer(self, offer_id: str) -> Offer:
        for offer in self.state.offers:
            if offer.id == offer_id:
                return offer
        raise ValueError("Oferta nao encontrada.")

    def _managed_offer_folder(self, offer: Offer) -> Path | None:
        root_text = self.state.settings.creative_root_folder.strip()
        if not root_text:
            return None
        root = Path(root_text).expanduser().resolve()
        folder = (root / offer.slug).resolve()
        try:
            folder.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("A pasta da oferta esta fora da central configurada.") from exc
        return folder

    def _restore_managed_audio_folders(self) -> None:
        root_text = self.state.settings.creative_root_folder.strip()
        if not root_text:
            return
        root = Path(root_text).expanduser().resolve()
        changed = False
        for index, offer in enumerate(self.state.offers):
            restored = ensure_offer_directories(root, offer)
            if restored != offer:
                self.state.offers[index] = restored
                changed = True
        if changed:
            self.store.save(self.state)

    def _save(self) -> None:
        self.store.save(self.state)


class HubRequestHandler(SimpleHTTPRequestHandler):
    server: "HubServer"

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = _request_path(self.path)
        if path == "/api/state":
            return _json_response(self, self.server.service.public_state())
        if path == "/api/job":
            return _json_response(self, self.server.service.job_state())
        if path == "/api/voices":
            try:
                provider = parse_qs(parsed.query).get("provider", ["clone"])[0]
                return _json_response(self, {"voices": self.server.service.list_voices(provider)})
            except (ValueError, VoiceProviderError) as error:
                return _json_response(self, {"error": str(error)}, 422)
        if path == "/api/video":
            requested = Path(parse_qs(parsed.query).get("path", [""])[0])
            return self._serve_video(requested)
        if path == "/api/music":
            requested = Path(parse_qs(parsed.query).get("path", [""])[0])
            return self._serve_music(requested)
        return self._serve_web(path)

    def do_POST(self) -> None:
        self._write_route("POST")

    def do_PUT(self) -> None:
        self._write_route("PUT")

    def do_DELETE(self) -> None:
        self._write_route("DELETE")

    def _write_route(self, method: str) -> None:
        try:
            path = _request_path(self.path)
            payload = _read_json(self)
            if method == "POST" and path == "/api/copies":
                return _json_response(self, {"copy": copy_to_dict(self.server.service.create_copy(payload))}, 201)
            if method == "POST" and path == "/api/offers":
                return _json_response(self, {"offer": offer_to_dict(self.server.service.create_offer(payload))}, 201)
            if method == "PUT" and path == "/api/settings":
                settings = self.server.service.update_settings(payload)
                return _json_response(self, {"settings": settings_to_dict(settings, include_secret=False)})
            if method == "POST" and path == "/api/select-folder":
                selected = self.server.service.select_folder(str(payload.get("current_path", "")))
                return _json_response(self, {"path": selected, "cancelled": not bool(selected)})
            if method == "POST" and path == "/api/select-file":
                selected = self.server.service.select_file(str(payload.get("current_path", "")))
                return _json_response(self, {"path": selected, "cancelled": not bool(selected)})
            if method == "POST" and path == "/api/select-font":
                selected = self.server.service.select_font(str(payload.get("current_path", "")))
                return _json_response(self, {"path": selected, "cancelled": not bool(selected)})
            if method == "POST" and path == "/api/fonts/import":
                return _json_response(self, {"available_fonts": self.server.service.import_font(str(payload.get("font_path", "")))})
            if method == "POST" and path == "/api/headline-preview":
                return _binary_response(self, self.server.service.headline_preview(payload), "image/png")
            if method == "POST" and path == "/api/voice/generate":
                self.server.service.start_voice_generation(payload.get("copy_ids", []))
                return _json_response(self, {"ok": True}, 202)
            if method == "POST" and path == "/api/production/batch":
                self.server.service.start_production(
                    "batch",
                    [],
                    str(payload.get("scope", "all")),
                    str(payload.get("batch_mode", "automatic")),
                    payload.get("batch_names"),
                )
                return _json_response(self, {"ok": True}, 202)
            if method == "POST" and path == "/api/production/test":
                self.server.service.start_production("test", payload.get("copy_ids", []))
                return _json_response(self, {"ok": True}, 202)
            if method == "POST" and path in {"/api/render/test", "/api/render/batch"}:
                self.server.service.start_render(payload.get("copy_ids", []), test_only=path.endswith("/test"))
                return _json_response(self, {"ok": True}, 202)
            if method == "POST" and path == "/api/open-output":
                folder = Path(self.server.service.state.active_offer.output_folder)
                folder.mkdir(parents=True, exist_ok=True)
                os.startfile(str(folder))
                return _json_response(self, {"ok": True})
            if method == "POST" and path == "/api/open-video":
                video = Path(str(payload.get("video_path", "")))
                self._ensure_output_video(video)
                os.startfile(str(video))
                return _json_response(self, {"ok": True})
            offer_id, offer_action = _offer_route(path)
            if offer_id and method == "POST" and offer_action == "activate":
                return _json_response(self, {"offer": offer_to_dict(self.server.service.activate_offer(offer_id))})
            if offer_id and method == "POST" and offer_action == "manual-audio/import":
                result = self.server.service.import_manual_audio(offer_id)
                return _json_response(
                    self,
                    {
                        "imported": [copy_to_dict(copy) for copy in result.imported],
                        "imported_count": len(result.imported),
                        "skipped": result.skipped,
                        "skipped_count": len(result.skipped),
                        "empty": result.empty,
                    },
                )
            if offer_id and method == "POST" and offer_action == "open-folder":
                self.server.service.open_offer_folder(offer_id, str(payload.get("field", "")))
                return _json_response(self, {"ok": True})
            if offer_id and method == "PUT" and offer_action is None:
                return _json_response(self, {"offer": offer_to_dict(self.server.service.update_offer(offer_id, payload))})
            if offer_id and method == "DELETE" and offer_action is None:
                self.server.service.delete_offer(offer_id)
                return _json_response(self, {"ok": True})
            copy_id, action = _copy_route(path)
            if copy_id and method == "PUT" and action is None:
                return _json_response(self, {"copy": copy_to_dict(self.server.service.update_copy(copy_id, payload))})
            if copy_id and method == "DELETE" and action is None:
                self.server.service.delete_copy(copy_id)
                return _json_response(self, {"ok": True})
            if copy_id and method == "POST" and action == "duplicate":
                return _json_response(self, {"copy": copy_to_dict(self.server.service.duplicate_copy(copy_id))}, 201)
            if copy_id and method == "POST" and action == "audio":
                return _json_response(self, {"copy": copy_to_dict(self.server.service.attach_audio(copy_id, str(payload.get("audio_path", ""))))})
            return _json_response(self, {"error": "Rota nao encontrada."}, 404)
        except (VoiceProviderUnavailable, VoiceProviderError) as exc:
            return _json_response(self, {"error": str(exc)}, 422)
        except (ValueError, RuntimeError) as exc:
            return _json_response(self, {"error": str(exc)}, 422)
        except Exception as exc:
            return _json_response(self, {"error": str(exc), "details": traceback.format_exc()}, 500)

    def _serve_web(self, path: str) -> None:
        target = WEB_DIR / "index.html" if path == "/" else (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR not in target.parents and target != WEB_DIR / "index.html":
            return self.send_error(403)
        self._send_file(target)

    def _serve_video(self, video: Path) -> None:
        try:
            self._ensure_output_video(video)
        except ValueError:
            return self.send_error(403)
        self._send_file(video)

    def _serve_music(self, music: Path) -> None:
        try:
            root = MUSIC_ROOT.resolve()
            if not music.exists() or not music.is_file() or root not in music.resolve().parents:
                raise ValueError
        except ValueError:
            return self.send_error(403)
        self._send_file(music)

    def _ensure_output_video(self, video: Path) -> None:
        output = Path(self.server.service.state.active_offer.output_folder).resolve()
        if not video.exists() or not video.is_file() or output not in video.resolve().parents:
            raise ValueError("Video nao encontrado na pasta de saida.")

    def _send_file(self, target: Path) -> None:
        if not target.exists() or not target.is_file():
            return self.send_error(404)
        size = target.stat().st_size
        start = 0
        end = max(size - 1, 0)
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes=") and size:
            try:
                requested_start, requested_end = range_header.removeprefix("bytes=").split("-", 1)
                if requested_start:
                    start = int(requested_start)
                    end = int(requested_end) if requested_end else end
                else:
                    suffix_length = int(requested_end)
                    start = max(size - suffix_length, 0)
                if start < 0 or start >= size or end < start:
                    raise ValueError
                end = min(end, size - 1)
                status = 206
            except (TypeError, ValueError):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with target.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class HubServer(ThreadingHTTPServer):
    service: HubService


def create_server(
    data_root: Path = ROOT,
    port: int = PORT,
    render_func=render_cards,
    voice_provider_factory=OpenSpeakerVoiceProvider,
    folder_picker=pick_folder,
    file_picker=pick_file,
    font_picker=pick_font,
    folder_opener=os.startfile,
    headline_preview_renderer=render_headline_preview,
    production_coordinator_factory=None,
) -> HubServer:
    server = HubServer(("127.0.0.1", port), HubRequestHandler)
    server.service = HubService(
        Path(data_root),
        render_func=render_func,
        voice_provider_factory=voice_provider_factory,
        folder_picker=folder_picker,
        file_picker=file_picker,
        font_picker=font_picker,
        folder_opener=folder_opener,
        headline_preview_renderer=headline_preview_renderer,
        production_coordinator_factory=production_coordinator_factory,
    )
    return server


def _read_json(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _binary_response(handler: SimpleHTTPRequestHandler, body: bytes, content_type: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _request_path(raw_path: str) -> str:
    path = urlparse(raw_path).path.rstrip("/")
    return path or "/"


def _copy_route(path: str) -> tuple[str | None, str | None]:
    parts = path.strip("/").split("/")
    if len(parts) < 3 or parts[:2] != ["api", "copies"]:
        return None, None
    return parts[2], parts[3] if len(parts) == 4 else None


def _offer_route(path: str) -> tuple[str | None, str | None]:
    parts = path.strip("/").split("/")
    if len(parts) < 3 or parts[:2] != ["api", "offers"]:
        return None, None
    return parts[2], "/".join(parts[3:]) if len(parts) > 3 else None


def _initial_folder(value: str) -> Path:
    path = Path(value.strip().strip('"')) if value.strip() else Path.home()
    if path.is_file():
        return path.parent
    if path.is_dir():
        return path
    return path.parent if path.parent.is_dir() else Path.home()


if __name__ == "__main__":
    server = create_server()
    print(f"Creative Hub em http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
