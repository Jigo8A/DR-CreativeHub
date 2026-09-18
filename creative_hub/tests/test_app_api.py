import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from app import create_server
from video_bridge import RenderResult


class ServerClient:
    def __init__(self, server) -> None:
        self.base_url = f"http://127.0.0.1:{server.server_port}"

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def request_bytes(self, method: str, path: str, payload: dict | None = None) -> tuple[int, bytes, str]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=3) as response:
            return response.status, response.read(), response.headers.get_content_type()


class AppApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.server = create_server(self.root, port=0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temporary.cleanup()

    def test_create_copy_persists_and_returns_card(self) -> None:
        status, payload = self.client.request("POST", "/api/copies", {"title": "Nova", "text": "Uma copy"})

        self.assertEqual(status, 201)
        self.assertEqual(payload["copy"]["title"], "Nova")
        state_status, state = self.client.request("GET", "/api/state")
        self.assertEqual(state_status, 200)
        self.assertEqual(state["copies"][0]["id"], payload["copy"]["id"])

    def test_delete_copy_removes_it_from_the_active_offer(self) -> None:
        _, created = self.client.request("POST", "/api/copies", {"title": "Remover", "text": "Texto"})

        status, _ = self.client.request("DELETE", f"/api/copies/{created['copy']['id']}")
        _, state = self.client.request("GET", "/api/state")

        self.assertEqual(status, 200)
        self.assertEqual(state["copies"], [])

    def test_public_state_exposes_the_font_catalog_owned_by_creative_hub(self) -> None:
        status, state = self.client.request("GET", "/api/state")

        self.assertEqual(status, 200)
        self.assertIn("available_fonts", state)
        self.assertIsInstance(state["available_fonts"], list)

    def test_video_route_streams_only_the_requested_byte_range_from_the_active_offer_output(self) -> None:
        output = self.root / "output"
        output.mkdir()
        video = output / "anuncio.mp4"
        video.write_bytes(b"0123456789")
        self.server.service.state.active_offer.output_folder = str(output)
        request = Request(
            f"{self.client.base_url}/api/video?path={quote(str(video))}",
            headers={"Range": "bytes=2-5"},
        )

        with urlopen(request, timeout=3) as response:
            body = response.read()

        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.headers.get_content_type(), "video/mp4")
        self.assertEqual(body, b"2345")

    def test_music_route_only_serves_files_from_the_hub_music_library(self) -> None:
        import app

        music_root = self.root / "musicas"
        track = music_root / "ukulele" / "faixa.mp3"
        track.parent.mkdir(parents=True)
        track.write_bytes(b"musica")
        previous_root = app.MUSIC_ROOT
        app.MUSIC_ROOT = music_root
        try:
            status, body, content_type = self.client.request_bytes("GET", f"/api/music?path={quote(str(track))}")
        finally:
            app.MUSIC_ROOT = previous_root

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "audio/mpeg")
        self.assertEqual(body, b"musica")

    def test_copy_can_store_an_individual_headline_for_rendering(self) -> None:
        _, created = self.client.request("POST", "/api/copies", {"title": "Ad", "text": "Texto"})
        headline = {"headline_text": "TITULO", "headline_duration": 2.5, "headline_font_size": 54}

        status, payload = self.client.request("PUT", f"/api/copies/{created['copy']['id']}", {"headline": headline})

        self.assertEqual(status, 200)
        self.assertEqual(payload["copy"]["headline"], headline)

    def test_create_offer_makes_it_active_and_isolates_its_copies(self) -> None:
        _, first = self.client.request("POST", "/api/offers", {"name": "Criancas"})
        self.client.request("POST", "/api/copies", {"title": "Copy kids", "text": "Texto"})
        status, second = self.client.request("POST", "/api/offers", {"name": "Musicais"})
        self.client.request("POST", "/api/copies", {"title": "Copy music", "text": "Texto"})
        _, state = self.client.request("GET", "/api/state")

        self.assertEqual(status, 201)
        self.assertEqual(state["active_offer_id"], second["offer"]["id"])
        self.assertEqual([copy["title"] for copy in state["copies"]], ["Copy music"])
        self.assertEqual(len(state["offers"]), 3)
        self.assertEqual(first["offer"]["name"], "Criancas")

    def test_delete_offer_removes_only_its_managed_folder_and_activates_another_offer(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})
        managed_folder = central / "azeitona"
        marker = managed_folder / "output" / "resultado.mp4"
        marker.write_text("video", encoding="utf-8")

        status, _ = self.client.request("DELETE", f"/api/offers/{created['offer']['id']}")
        _, state = self.client.request("GET", "/api/state")

        self.assertEqual(status, 200)
        self.assertFalse(managed_folder.exists())
        self.assertNotIn(created["offer"]["id"], [offer["id"] for offer in state["offers"]])
        self.assertNotEqual(state["active_offer_id"], created["offer"]["id"])

    def test_global_settings_do_not_clear_the_audio_folder_created_for_an_offer(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})

        self.client.request("PUT", "/api/settings", {"manual_audio_folder": "", "subtitle_font_size": 32})
        _, state = self.client.request("GET", "/api/state")

        api_audio_folder = str(central / "azeitona" / "audios_api")
        self.assertEqual(created["offer"]["audio_folder"], api_audio_folder)
        self.assertEqual(created["offer"]["api_audio_folder"], api_audio_folder)
        self.assertEqual(state["active_offer"]["audio_folder"], api_audio_folder)
        self.assertEqual(state["active_offer"]["api_audio_folder"], api_audio_folder)

    def test_manual_audio_import_route_archives_audio_and_persists_a_copy(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})
        inbox = Path(created["offer"]["manual_audio_inbox_folder"])
        source = inbox / "Anuncio 22.wav"
        source.write_bytes(b"audio")

        status, payload = self.client.request("POST", f"/api/offers/{created['offer']['id']}/manual-audio/import", {})
        _, state = self.client.request("GET", "/api/state")

        self.assertEqual(status, 200)
        self.assertEqual(payload["imported_count"], 1)
        self.assertFalse(payload["empty"])
        self.assertEqual(payload["imported"][0]["title"], "Anuncio 22")
        self.assertEqual(state["copies"][0]["title"], "Anuncio 22")
        self.assertTrue(Path(state["copies"][0]["audio_path"]).is_file())
        self.assertFalse(source.exists())

    def test_batch_submits_an_imported_manual_audio_without_copy_text(self) -> None:
        received = []
        completed = Event()

        class FakeCoordinator:
            def run(self, cards, _settings, _mode, _progress, batch_targets=None):
                received.extend(cards)
                completed.set()
                return []

        self.server.service.production_coordinator_factory = lambda: FakeCoordinator()
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})
        inbox = Path(created["offer"]["manual_audio_inbox_folder"])
        (inbox / "Anuncio 22.wav").write_bytes(b"audio")
        self.client.request("POST", f"/api/offers/{created['offer']['id']}/manual-audio/import", {})

        status, _ = self.client.request("POST", "/api/production/batch", {"scope": "active"})

        self.assertEqual(status, 202)
        self.assertTrue(completed.wait(timeout=3))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].card.audio_source, "manual")
        self.assertEqual(received[0].card.text, "")

    def test_attaching_manual_audio_invalidates_prior_render_artifacts(self) -> None:
        _, created = self.client.request("POST", "/api/copies", {"title": "Anuncio", "text": "Copy antiga"})
        card = self.server.service._find_copy(created["copy"]["id"])
        card.audio_signature = "audio-antigo"
        card.transcript_signature = "transcricao-antiga"
        card.render_signature = "render-antigo"
        card.transcript_path = str(self.root / "transcricao.json")
        card.subtitle_path = str(self.root / "legenda.ass")
        card.output_path = str(self.root / "resultado.mp4")
        audio = self.root / "novo.wav"
        audio.write_bytes(b"novo audio")

        status, payload = self.client.request("POST", f"/api/copies/{card.id}/audio", {"audio_path": str(audio)})

        self.assertEqual(status, 200)
        self.assertEqual(payload["copy"]["audio_source"], "manual")
        for field in ("audio_signature", "transcript_signature", "render_signature", "transcript_path", "subtitle_path", "output_path"):
            self.assertIsNone(payload["copy"][field])

    def test_manual_audio_import_route_returns_empty_inbox_as_success(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})

        status, payload = self.client.request("POST", f"/api/offers/{created['offer']['id']}/manual-audio/import", {})

        self.assertEqual(status, 200)
        self.assertTrue(payload["empty"])
        self.assertEqual(payload["imported_count"], 0)

    def test_manual_audio_import_route_rejects_invalid_folders(self) -> None:
        status, payload = self.client.request("POST", "/api/offers/default/manual-audio/import", {})

        self.assertEqual(status, 422)
        self.assertIn("entrada", payload["error"])

    def test_manual_audio_import_route_rejects_a_running_job(self) -> None:
        self.server.service.job["running"] = True

        status, payload = self.client.request("POST", "/api/offers/default/manual-audio/import", {})

        self.assertEqual(status, 422)
        self.assertIn("processamento", payload["error"])

    def test_manual_audio_import_rolls_back_files_and_state_when_save_fails(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, created = self.client.request("POST", "/api/offers", {"name": "Azeitona"})
        offer = self.server.service._find_offer(created["offer"]["id"])
        inbox = Path(offer.manual_audio_inbox_folder)
        source = inbox / "Anuncio 22.wav"
        source.write_bytes(b"audio")
        original_save = self.server.service.store.save

        def failing_save(_state) -> None:
            raise OSError("disco indisponivel")

        self.server.service.store.save = failing_save
        try:
            with self.assertRaisesRegex(OSError, "disco indisponivel"):
                self.server.service.import_manual_audio(offer.id)
        finally:
            self.server.service.store.save = original_save

        self.assertEqual(offer.copies, [])
        self.assertTrue(source.is_file())
        self.assertEqual(list(Path(offer.manual_audio_library_folder).rglob("*.wav")), [])

    def test_settings_persist_without_returning_voice_api_key(self) -> None:
        status, _ = self.client.request(
            "PUT",
            "/api/settings",
            {"subtitle_font_size": 34, "output_folder": r"C:\renders", "voice_api_key": "private-key"},
        )

        self.assertEqual(status, 200)
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["settings"]["subtitle_font_size"], 34)
        self.assertEqual(state["settings"]["voice_api_key"], "")
        self.assertTrue(state["settings"]["voice_api_configured"])

    def test_narration_speed_is_persisted_in_the_voice_settings(self) -> None:
        status, _ = self.client.request("PUT", "/api/settings", {"voice_speed": 1.12})

        self.assertEqual(status, 200)
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["settings"]["voice_speed"], 1.12)

    def test_render_concurrency_is_persisted_and_rejects_unsupported_values(self) -> None:
        status, _ = self.client.request("PUT", "/api/settings", {"render_concurrency": 1})

        self.assertEqual(status, 200)
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["settings"]["render_concurrency"], 1)

        invalid_status, _ = self.client.request("PUT", "/api/settings", {"render_concurrency": 3})
        self.assertEqual(invalid_status, 422)

    def test_safe_zone_visibility_is_persisted_without_affecting_render_settings(self) -> None:
        status, _ = self.client.request("PUT", "/api/settings", {"safe_zone_visible": True})

        self.assertEqual(status, 200)
        _, state = self.client.request("GET", "/api/state")
        self.assertTrue(state["settings"]["safe_zone_visible"])
        self.assertEqual(state["settings"]["subtitle_mode"], "highlight")

    def test_headline_preview_is_rendered_as_a_png_from_the_same_settings(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        received = []

        def fake_preview_renderer(settings):
            received.append(settings)
            return b"preview-png"

        self.server = create_server(self.root, port=0, headline_preview_renderer=fake_preview_renderer)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)

        status, body, content_type = self.client.request_bytes(
            "POST",
            "/api/headline-preview",
            {"headline_text": "Linha um\nLinha dois", "headline_font_size": 52, "headline_enabled": True},
        )

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertEqual(body, b"preview-png")
        self.assertEqual(received[0].headline_text, "Linha um\nLinha dois")
        self.assertEqual(received[0].headline_font_size, 52)

    def test_blank_key_update_does_not_erase_the_saved_api_key(self) -> None:
        self.client.request("PUT", "/api/settings", {"voice_api_key": "private-key"})

        self.client.request("PUT", "/api/settings", {"voice_api_key": ""})

        self.assertEqual(self.server.service.state.settings.voice_api_key, "private-key")

    def test_assemblyai_key_is_saved_but_never_returned_by_the_state_api(self) -> None:
        status, _ = self.client.request(
            "PUT",
            "/api/settings",
            {"transcription_provider": "assemblyai", "assemblyai_api_key": "private-assembly-key"},
        )

        self.assertEqual(status, 200)
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["settings"]["transcription_provider"], "assemblyai")
        self.assertEqual(state["settings"]["assemblyai_api_key"], "")
        self.assertTrue(state["settings"]["assemblyai_api_configured"])

    def test_broll_file_picker_returns_the_selected_video_path(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        expected = self.root / "produto.mp4"
        received = []

        def fake_file_picker(initial):
            received.append(initial)
            return str(expected)

        self.server = create_server(self.root, port=0, file_picker=fake_file_picker)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        status, payload = self.client.request("POST", "/api/select-file", {"current_path": f'"{expected}"'})

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"path": str(expected), "cancelled": False})
        self.assertEqual(received, [expected.parent])

    def test_open_offer_folder_opens_the_configured_media_folder(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        opened = []
        takes_folder = self.root / "takes"
        takes_folder.mkdir()

        self.server = create_server(self.root, port=0, folder_opener=lambda path: opened.append(path))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        self.client.request("PUT", "/api/offers/default", {"takes_folder": str(takes_folder)})

        status, payload = self.client.request("POST", "/api/offers/default/open-folder", {"field": "takes_folder"})

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(opened, [str(takes_folder)])

    def test_rejects_a_second_folder_picker_request_while_the_first_is_open(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        picker_started = Event()
        release_picker = Event()
        calls = []

        def fake_folder_picker(initial):
            calls.append(initial)
            if len(calls) == 1:
                picker_started.set()
                release_picker.wait(timeout=3)
            return str(self.root)

        self.server = create_server(self.root, port=0, folder_picker=fake_folder_picker)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        first_response = []
        first = Thread(target=lambda: first_response.append(self.client.request("POST", "/api/select-folder", {})))
        first.start()
        self.assertTrue(picker_started.wait(timeout=2))

        status, payload = self.client.request("POST", "/api/select-folder", {})
        release_picker.set()
        first.join(timeout=3)

        self.assertEqual(status, 422)
        self.assertIn("seletor", payload["error"])
        self.assertEqual(len(calls), 1)

    def test_api_generation_without_provider_returns_clear_error(self) -> None:
        _, created = self.client.request("POST", "/api/copies", {"title": "Nova", "text": "Uma copy"})
        status, payload = self.client.request("POST", "/api/voice/generate", {"copy_ids": [created["copy"]["id"]]})

        self.assertEqual(status, 422)
        self.assertIn("chave da API", payload["error"])

    def test_production_test_requires_exactly_one_selected_copy(self) -> None:
        status, payload = self.client.request("POST", "/api/production/test", {"copy_ids": []})

        self.assertEqual(status, 422)
        self.assertIn("uma copy", payload["error"])

    def test_production_batch_accepts_all_copies_without_a_selection(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        self.client.request("POST", "/api/offers", {"name": "Produto A"})
        self.client.request("POST", "/api/copies", {"title": "Um", "text": "Copy um"})
        self.client.request("POST", "/api/copies", {"title": "Dois", "text": "Copy dois"})

        status, _ = self.client.request("POST", "/api/production/batch", {})

        self.assertEqual(status, 202)

    def test_production_batch_accepts_the_active_offer_scope(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        self.client.request("POST", "/api/offers", {"name": "Produto A"})
        self.client.request("POST", "/api/copies", {"title": "Somente atual", "text": "Copy atual"})

        status, _ = self.client.request("POST", "/api/production/batch", {"scope": "active"})

        self.assertEqual(status, 202)

    def test_all_offers_custom_batch_builds_one_target_per_included_offer(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        received = []
        completed = Event()

        class FakeCoordinator:
            def run(self, cards, settings, mode, progress, batch_targets=None):
                received.append((cards, mode, batch_targets))
                completed.set()
                return []

        self.server = create_server(self.root, port=0, production_coordinator_factory=lambda: FakeCoordinator())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, first = self.client.request("POST", "/api/offers", {"name": "Produto A"})
        self.client.request("POST", "/api/copies", {"title": "Copy A", "text": "Texto A"})
        _, second = self.client.request("POST", "/api/offers", {"name": "Produto B"})
        self.client.request("POST", "/api/copies", {"title": "Copy B", "text": "Texto B"})

        status, _ = self.client.request(
            "POST",
            "/api/production/batch",
            {
                "scope": "all",
                "batch_mode": "custom",
                "batch_names": {first["offer"]["id"]: "setembro-a", second["offer"]["id"]: "setembro-b"},
            },
        )

        self.assertEqual(status, 202)
        self.assertTrue(completed.wait(timeout=3))
        cards, mode, targets = received[0]
        self.assertEqual(mode, "batch")
        self.assertEqual({item.offer.id for item in cards}, {first["offer"]["id"], second["offer"]["id"]})
        self.assertEqual({offer_id: target.name for offer_id, target in targets.items()}, {
            first["offer"]["id"]: "setembro-a",
            second["offer"]["id"]: "setembro-b",
        })

    def test_custom_batch_rejects_a_missing_name_for_an_included_offer(self) -> None:
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        self.client.request("POST", "/api/offers", {"name": "Produto A"})
        self.client.request("POST", "/api/copies", {"title": "Copy A", "text": "Texto A"})

        status, payload = self.client.request(
            "POST", "/api/production/batch", {"scope": "all", "batch_mode": "custom", "batch_names": {}}
        )

        self.assertEqual(status, 422)
        self.assertIn("nome", payload["error"].lower())

    def test_voice_generation_updates_each_selected_card_with_downloaded_audio(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

        class FakeVoiceProvider:
            def generate(self, card, settings, progress_callback=None, destination=None):
                if progress_callback:
                    progress_callback("Baixando audio...", 94)
                output = Path(destination)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"audio")
                return output

        self.server = create_server(self.root, port=0, voice_provider_factory=FakeVoiceProvider)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        central = self.root / "Ofertas"
        self.client.request("PUT", "/api/settings", {"creative_root_folder": str(central)})
        _, offer = self.client.request("POST", "/api/offers", {"name": "Produto A"})
        _, created = self.client.request("POST", "/api/copies", {"title": "Narracao", "text": "Uma copy pronta"})
        copy_id = created["copy"]["id"]
        self.client.request(
            "PUT",
            "/api/settings",
            {"voice_api_key": "key", "voice_name": "minimax_male-qn-qingse"},
        )
        status, _ = self.client.request("POST", "/api/voice/generate", {"copy_ids": [copy_id]})
        self.assertEqual(status, 202)

        job = {}
        for _ in range(20):
            _, job = self.client.request("GET", "/api/job")
            if not job["running"]:
                break
        self.assertEqual(job["status"], "Narracoes finalizadas")
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["copies"][0]["status"], "audio_ready")
        self.assertEqual(Path(state["copies"][0]["audio_path"]).parent, Path(offer["offer"]["api_audio_folder"]))

    def test_voice_library_returns_normalized_choices_without_exposing_api_key(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

        received = []

        class FakeVoiceProvider:
            def list_voices(self, settings, provider):
                received.append((settings.voice_api_key, provider))
                return [{"id": "clone_maria", "name": "Maria - minha voz", "provider": "clone", "language": "Portuguese"}]

            def generate(self, card, settings, progress_callback=None):
                raise AssertionError("Nao deve gerar audio ao consultar vozes")

        self.server = create_server(self.root, port=0, voice_provider_factory=FakeVoiceProvider)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)
        self.client.request("PUT", "/api/settings", {"voice_api_key": "private-key"})

        status, payload = self.client.request("GET", "/api/voices?provider=clone")

        self.assertEqual(status, 200)
        self.assertEqual(payload["voices"], [{"id": "clone_maria", "name": "Maria - minha voz", "provider": "clone", "language": "Portuguese"}])
        self.assertEqual(received, [("private-key", "clone")])
        self.assertNotIn("voice_api_key", payload)

    def test_copy_can_choose_a_voice_that_overrides_the_default(self) -> None:
        _, created = self.client.request("POST", "/api/copies", {"title": "Nova", "text": "Uma copy"})

        status, payload = self.client.request("PUT", f"/api/copies/{created['copy']['id']}", {"voice_name": "clone_maria"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["copy"]["voice_name"], "clone_maria")

    def test_test_render_runs_selected_manual_audio_and_persists_result(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

        takes = self.root / "takes"
        takes.mkdir()
        audio = self.root / "copy.wav"
        audio.write_bytes(b"audio")

        def fake_render(cards, settings, test_only):
            card = cards[0]
            card.output_path = str(self.root / "output" / "copy.mp4")
            card.status = "rendered"
            return [RenderResult(card.id, "completed", card.output_path, None)]

        self.server = create_server(self.root, port=0, render_func=fake_render)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ServerClient(self.server)

        _, created = self.client.request("POST", "/api/copies", {"title": "Teste", "text": "Uma copy"})
        copy_id = created["copy"]["id"]
        self.client.request("PUT", "/api/settings", {"takes_folder": str(takes), "output_folder": str(self.root / "output")})
        self.client.request("POST", f"/api/copies/{copy_id}/audio", {"audio_path": str(audio)})

        status, _ = self.client.request("POST", "/api/render/test", {"copy_ids": [copy_id]})
        self.assertEqual(status, 202)

        job = {}
        for _ in range(20):
            _, job = self.client.request("GET", "/api/job")
            if not job["running"]:
                break
        self.assertEqual(job["status"], "Teste finalizado")
        _, state = self.client.request("GET", "/api/state")
        self.assertEqual(state["copies"][0]["output_path"], str(self.root / "output" / "copy.mp4"))
