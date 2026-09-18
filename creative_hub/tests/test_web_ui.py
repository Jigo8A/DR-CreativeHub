from pathlib import Path
import json
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent


class WebUiTests(unittest.TestCase):
    def test_ui_exposes_a_persistent_collapsible_icon_sidebar(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        for token in ["sidebarToggle", "sidebar-collapsed", "creative-hub-sidebar-collapsed", "setSidebarCollapsed"]:
            self.assertIn(token, script)
        self.assertIn('id="sidebarToggle"', html)
        self.assertIn(".app-shell.sidebar-collapsed", styles)
        self.assertIn("will-change: transform, opacity", styles)
        self.assertIn("padding: 2px 6px 27px", styles)
        self.assertIn("minmax(250px, 280px)", styles)
        self.assertIn(".nav-item > svg:first-child", styles)
        self.assertNotIn(".sidebar-collapsed .nav-item > svg:first-child", styles)
        self.assertIn('showView("integrations")', script)

    def test_ui_exposes_headline_controls_and_center_alignment_guides(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["headline_text", "headline_duration", "headlinePreview", "headlineGuides", "snapToCenter"]:
            self.assertIn(token, script)

    def test_ui_exposes_independent_font_and_outline_controls(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in [
            'data-setting="subtitle_font_name"',
            'data-setting="subtitle_outline_enabled"',
            'data-setting="subtitle_outline_size"',
            'colorControl("subtitle_highlight_color"',
            'data-setting="headline_font_name"',
            'data-setting="headline_outline_enabled"',
            'data-setting="headline_outline_size"',
        ]:
            self.assertIn(token, script)

    def test_editing_preview_reflects_caption_style_and_uppercase_choice(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        preview = script[script.index("function syncPreview") : script.index("function scheduleHeadlineRender")]
        caption_text = script[script.index("function captionPreviewText") : script.index("function escapeHtml")]

        self.assertIn("preview.querySelector(\"span\").innerHTML = captionPreviewText(s)", preview)
        self.assertIn("subtitle_force_caps", caption_text)
        self.assertIn("<em>legenda</em>", caption_text)

    def test_editing_header_stays_visible_while_settings_scroll(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('document.body.classList.toggle("edit-active", view === "edit")', script)
        self.assertIn(".edit-active .topbar", styles)
        self.assertIn("position: sticky", styles)

    def test_hex_color_normalizer_accepts_six_digit_hex_without_hash(self) -> None:
        result = subprocess.run(
            [
                "node",
                "-e",
                "const colors = require('./web/color_utils.js'); console.log(JSON.stringify([colors.normalizeHexColor('fcff00'), colors.normalizeHexColor('#fcff00'), colors.normalizeHexColor('xyz')]));",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["#FCFF00", "#FCFF00", None])

    def test_ui_exposes_a_collapsible_hex_color_entry(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("hex-toggle", script)
        self.assertIn("hex-input", script)
        self.assertIn('return `<div class="color-control">', script)
        self.assertIn("button.onclick = toggleHex", script)

    def test_ui_exposes_global_batch_and_selection_controls(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["Gerar esta oferta", "Gerar todas as ofertas", "renderActiveOffer", "renderAllOffers", "scope === \"active\"", "toggleAllCopies", "Desmarcar todas desta aba", "createCopyInWorkspace", "/api/production/batch", "/api/production/test"]:
            self.assertIn(token, script)

    def test_batch_setup_accepts_manual_audio_without_copy_text(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function isBatchEligible", script)
        self.assertIn('copy.audio_source === "manual"', script)
        self.assertIn("isBatchEligible(copy)", script)

    def test_headline_catalog_keeps_in_sync_when_a_workspace_copy_is_removed(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function syncOfferCopy", script)
        self.assertIn("function removeOfferCopy", script)
        delete_copy = script[script.index("async function deleteCopy") : script.index("async function attachAudio")]
        self.assertIn("removeOfferCopy(id)", delete_copy)

    def test_ui_opens_a_rendered_video_in_an_in_app_player_modal(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        for token in ["videoPlayerModal", "nativeVideoPlayer", "openVideoPlayer", "closeVideoPlayer", "/api/video?path="]:
            self.assertIn(token, script)
        self.assertIn(".video-player-modal", styles)

    def test_ui_uses_creative_hubs_local_font_catalog_and_import_control(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["available_fonts", "importLocalFont", "/api/select-font", "/api/fonts/import", "Fontes locais"]:
            self.assertIn(token, script)

    def test_ui_exposes_offer_workspace_controls(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["offerWorkspaceHtml", "offer-tabs", "offer-tab-add", "createOffer", "activateOffer", "/api/offers", "active_offer"]:
            self.assertIn(token, script)

    def test_ui_exposes_a_native_headline_workspace_without_an_embedded_react_editor(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("headline-studio", script)
        self.assertIn("Abrir headlines", script)
        self.assertIn("renderHeadlineStudioView", script)
        self.assertIn("native-headline-input", script)
        self.assertIn("Salvar headline desta copy", script)
        self.assertIn("bindNativeHeadlinePreview", script)
        self.assertIn("nativeHeadlineWidthHandle", script)
        self.assertIn("moveNativeHeadlinePreview", script)
        self.assertIn('data-view="headline-studio"', html)
        self.assertNotIn('src="/headline-studio/index.html"', html)

    def test_offers_use_an_in_app_catalog_and_modal_instead_of_browser_prompts(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        for token in ["offer-catalog", "offer-details", "openCreateOfferModal", "openDeleteOfferModal", "confirmOfferModal", '"DELETE"']:
            self.assertIn(token, script)
        self.assertNotIn("window.prompt", script)
        self.assertIn('id="offerModal"', html)

    def test_ui_separates_offer_media_editing_and_api_integrations(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        for token in ["renderOffersView", "renderIntegrationsView", "renderPerformanceView", "renderTranscriptionControl", "goToIntegrations", "integration", "render_concurrency"]:
            self.assertIn(token, script)
        for token in ['data-view="offers"', 'data-view="integrations"', 'data-view="performance"', 'id="settingsMenu"']:
            self.assertIn(token, html)

    def test_offers_view_exposes_api_and_manual_audio_folders(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in [
            '"Pasta de audios API"',
            '"Entrada de audios manuais"',
            '"Biblioteca de audios manuais"',
            '"api_audio_folder"',
            '"manual_audio_inbox_folder"',
            '"manual_audio_library_folder"',
        ]:
            self.assertIn(token, script)

    def test_workspace_imports_manual_audio_and_configures_batch_names_in_a_hub_modal(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in [
            "importManualAudio",
            "manual-audio/import",
            "openBatchSetup",
            "batch_names",
            "batch_mode",
            'id="batchSetupModal"',
        ]:
            self.assertIn(token, script)

    def test_empty_offer_keeps_manual_audio_import_available(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        empty_view = script[script.index("if (!state.copies.length)") : script.index("const allSelected", script.index("if (!state.copies.length)"))]

        self.assertIn("importManualAudio", empty_view)
        self.assertIn("Importar audios manuais", empty_view)
        self.assertIn("manual_audio_inbox_folder", empty_view)

    def test_batch_modal_scrolls_many_custom_offer_names_without_hiding_actions(self) -> None:
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("max-height: min(760px, calc(100vh - 40px))", styles)
        self.assertIn(".batch-setup-body", styles)
        self.assertIn("overflow-y: auto", styles)

    def test_editing_shows_the_assemblyai_connection_state(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("AssemblyAI configurada", script)
        self.assertIn("assemblyai_api_configured", script)
        self.assertIn('data-lucide="circle-check"', script)

    def test_exact_headline_preview_hides_the_fallback_text_shadow(self) -> None:
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".headline-preview.render-ready", styles)
        self.assertIn("text-shadow: none !important", styles)
        self.assertIn(".subtitle-preview.no-outline", styles)

    def test_preview_position_keeps_zero_as_a_valid_coordinate(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function numberSetting", script)
        self.assertIn('numberSetting(s.headline_x_position, .5)', script)

    def test_headline_preview_uses_the_ass_renderer_image_instead_of_browser_font_metrics(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('"/api/headline-preview"', script)
        self.assertIn("headlineRenderPreview", script)
        self.assertIn("URL.createObjectURL", script)

    def test_headline_keeps_the_last_exact_preview_visible_while_refreshing(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        schedule = script[script.index("function scheduleHeadlineRender") : script.index("async function loadHeadlineRender")]
        renderer = script[script.index("async function loadHeadlineRender") : script.index("async function createCopy")]
        visible_flow = schedule.split("if (!visible)", 1)[1].split("return;", 1)[1]

        self.assertNotIn('image.classList.remove("visible")', visible_flow)
        self.assertNotIn('fallback.classList.remove("render-ready")', visible_flow)
        self.assertIn("const stagedImage = new Image()", renderer)

    def test_headline_has_separate_preview_handles_for_width_height_and_both_axes(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["headlineWidthResizeHandle", "headlineHeightResizeHandle", "headlineCornerResizeHandle", 'bindHeadlineResizeHandle(widthHandle, "resize-width"', 'bindHeadlineResizeHandle(heightHandle, "resize-height"', 'bindHeadlineResizeHandle(cornerHandle, "resize-both"']:
            self.assertIn(token, script)

    def test_caption_preview_uses_the_no_wrap_behavior_of_the_render_engine(self) -> None:
        result = subprocess.run(
            [
                "node",
                "-e",
                "const metrics = require('./web/preview_metrics.js'); console.log(JSON.stringify(metrics.captionLayout()));",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"width": "max-content", "maxWidth": "none", "whiteSpace": "nowrap"},
        )

    def test_preview_metrics_scale_ass_font_size_to_the_visible_9_by_16_stage(self) -> None:
        result = subprocess.run(
            [
                "node",
                "-e",
                "const metrics = require('./web/preview_metrics.js'); console.log(JSON.stringify({ visible: metrics.visibleStageWidth(0), caption: metrics.captionMetrics(metrics.visibleStageWidth(0), 62) }));",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        metrics = json.loads(result.stdout)
        self.assertEqual(metrics["visible"], 310)
        self.assertAlmostEqual(metrics["caption"]["fontSize"], 26.694, places=3)
        self.assertAlmostEqual(metrics["caption"]["outline"], 1.292, places=3)

    def test_ui_has_offer_edit_and_integration_workspace_views(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('data-view="creative"', html)
        self.assertIn('data-view="offers"', html)
        self.assertIn('data-view="edit"', html)
        self.assertIn('data-view="integrations"', html)

    def test_ui_has_vertical_preview_and_render_actions(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("creativeSubtitlePreview", script)
        self.assertIn("/api/render/test", script)
        self.assertIn("/api/render/batch", script)

    def test_ui_exposes_card_audio_source_and_caption_controls(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ["audio_source", "status", "subtitle_x_position", "subtitle_y_position", "subtitle_font_size"]:
            self.assertIn(token, script)

    def test_ui_uses_a_supported_save_icon_name(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn('data-lucide="cloud-check"', html)
        self.assertNotIn('data-lucide="cloud-check"', script)
        self.assertIn('data-lucide="check"', html)

    def test_copy_text_fields_persist_while_editing(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('"input", event => scheduleCopyUpdate(id, { title: event.target.value })', script)
        self.assertIn('"input", event => scheduleCopyUpdate(id, { text: event.target.value })', script)

    def test_edit_layout_collapses_before_sidebar_causes_overflow(self) -> None:
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 1120px)", styles)

    def test_collapsible_sidebar_uses_compositor_friendly_label_animation(self) -> None:
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("will-change: transform, opacity", styles)
        self.assertIn(".nav-item > svg:first-child { position: absolute; left: 14px", styles)
        self.assertNotIn(".sidebar-collapsed .nav-item > svg:first-child", styles)
        self.assertNotIn(".sidebar-collapsed .engine-dot", styles)
        self.assertIn(".settings-menu.open { display: grid; min-height: 42px; }", styles)
        self.assertIn(".settings-menu.open .nav-subitem { width: 100%; }", styles)
        self.assertIn(".sidebar-footer { position: relative; display: block; min-height: 50px;", styles)
        self.assertIn(".engine-dot { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); }", styles)
        self.assertIn(".sidebar-footer > div { position: absolute; left: 38px; top: 50%;", styles)
        self.assertIn(".sidebar-collapsed .sidebar-footer > div { transform: translate(-10px, -50%); }", styles)
        self.assertNotIn(".sidebar-collapsed .sidebar-footer > div { position: absolute; }", styles)

    def test_offer_catalog_stacks_above_details_on_narrow_screens(self) -> None:
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".offers-manager { grid-template-columns: 1fr; }", styles)

    def test_subtitle_pointer_listeners_start_and_end_with_the_drag(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function beginSubtitleInteraction", script)
        self.assertIn('window.addEventListener("pointermove", moveSubtitlePreview)', script)
        self.assertIn('window.removeEventListener("pointermove", moveSubtitlePreview)', script)

    def test_ui_exposes_open_speaker_audio_generation_for_selected_cards(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("/api/voice/generate", script)
        self.assertIn("Gerar audios", script)

    def test_ui_uses_voice_library_selectors_for_api_audio(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("/api/voices", script)
        self.assertIn("Carregar vozes", script)
        self.assertIn("Usar voz padrao", script)
        self.assertIn("state.settings.voice_name = voiceLibrary[0].id", script)

    def test_ui_exposes_a_persistent_custom_narration_speed(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        for token in ['id="voiceSpeed"', 'min="0.5"', 'max="1.5"', 'step="0.01"', "state.settings.voice_speed"]:
            self.assertIn(token, script)

    def test_ui_restores_voice_library_when_api_is_already_configured(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("state.settings.voice_api_configured", script)
        self.assertIn("loadVoices({ automatic: true })", script)

    def test_ui_uses_a_file_picker_for_broll(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('offerFileInput("broll_path", "Video de B-roll"', script)
        self.assertIn('"/api/select-file"', script)

    def test_music_rule_control_uses_clear_modes_and_a_track_preview(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        controls = script[script.index("function musicRuleControls") : script.index("function manualAudioControl")]

        for token in ["music-mode-switch", "Padrao da oferta", "Personalizar", "music-custom-mode", "music-preview-track", "previewBackgroundMusic"]:
            self.assertIn(token, controls)

    def test_ui_exposes_local_and_assemblyai_transcription_choices(self) -> None:
        script = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-setting="transcription_provider"', script)
        self.assertIn('value="assemblyai"', script)
        self.assertIn("assemblyai_api_key", script)

    def test_headline_editor_keeps_the_experimental_emoji_picker_unplugged(self) -> None:
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "headline_workspace.css").read_text(encoding="utf-8")
        base_styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        editor = script[script.index("function renderHeadlineStudioView") : script.index("function bindHeadlineEmojiPicker")]

        self.assertNotIn('id="headlineEmojiPickerToggle"', editor)
        self.assertNotIn('bindHeadlineEmojiPicker(target)', editor)
        self.assertNotIn("CreativeHubAppleEmoji", styles + base_styles)
