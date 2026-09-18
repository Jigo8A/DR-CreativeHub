import unittest

from app import _creative_settings, _request_path, _select_windows_folder, _settings, _subtitle_settings, _video_url


class SettingsTests(unittest.TestCase):
    def test_strips_wrapping_quotes_from_pasted_windows_paths(self):
        settings = _settings(
            {
                "input_folder": '"C:\\Users\\PCGamerInfor\\Documents\\Appyon\\2. KellyNash\\13.09\\video 3"',
                "output_folder": '"C:\\Users\\PCGamerInfor\\Documents\\Appyon\\2. KellyNash\\13.09\\video 3\\output"',
            }
        )

        self.assertEqual(
            str(settings["input_folder"]),
            "C:\\Users\\PCGamerInfor\\Documents\\Appyon\\2. KellyNash\\13.09\\video 3",
        )
        self.assertEqual(
            str(settings["output_folder"]),
            "C:\\Users\\PCGamerInfor\\Documents\\Appyon\\2. KellyNash\\13.09\\video 3\\output",
        )

    def test_video_url_keeps_custom_output_path_addressable(self):
        url = _video_url("C:\\Users\\PCGamerInfor\\Documents\\Appyon\\2. KellyNash\\13.09\\video 3\\output\\final.mp4")

        self.assertTrue(url.startswith("/api/video?path="))
        self.assertIn("video%203", url)

    def test_folder_picker_returns_selected_windows_path(self):
        selected = _select_windows_folder(
            "C:\\base",
            askdirectory_func=lambda **kwargs: '"C:\\Users\\PCGamerInfor\\Videos\\Criativos"',
        )

        self.assertEqual(str(selected), "C:\\Users\\PCGamerInfor\\Videos\\Criativos")

    def test_request_path_ignores_query_and_trailing_slash(self):
        self.assertEqual(_request_path("/api/select-folder/?target=inputFolder"), "/api/select-folder")

    def test_folder_picker_uses_modern_explorer_dialog(self):
        import modern_folder_picker

        self.assertEqual(modern_folder_picker.CLSID_FILE_OPEN_DIALOG, "DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
        self.assertEqual(modern_folder_picker.FOS_PICKFOLDERS, 0x20)

    def test_folder_picker_no_longer_uses_powershell_script(self):
        import inspect
        import app

        source = inspect.getsource(app._select_windows_folder)

        self.assertNotIn("powershell", source.lower())
        self.assertNotIn("folder_picker.ps1", source)

    def test_reads_subtitle_settings_from_payload(self):
        settings = _settings(
            {
                "subtitle_mode": "highlight",
                "subtitle_x_position": "0.42",
                "subtitle_y_position": "0.72",
                "subtitle_font_size": "28",
                "subtitle_words_per_line": "3",
                "subtitle_force_caps": False,
            }
        )

        self.assertEqual(settings["subtitle_mode"], "highlight")
        self.assertEqual(settings["subtitle_x_position"], 0.42)
        self.assertEqual(settings["subtitle_y_position"], 0.72)
        self.assertEqual(settings["subtitle_font_size"], 28)
        self.assertEqual(settings["subtitle_words_per_line"], 3)
        self.assertFalse(settings["subtitle_force_caps"])

    def test_builds_reusable_subtitle_settings_for_caption_batch(self):
        settings = _subtitle_settings(
            {
                "subtitle_mode": "highlight",
                "subtitle_x_position": 0.25,
                "subtitle_y_position": 0.70,
                "subtitle_font_size": 36,
                "subtitle_words_per_line": 2,
                "subtitle_force_caps": False,
            }
        )

        self.assertEqual(settings.mode, "highlight")
        self.assertEqual(settings.x_position, 0.25)
        self.assertEqual(settings.y_position, 0.70)
        self.assertEqual(settings.font_size, 36)
        self.assertEqual(settings.max_words_per_line, 2)
        self.assertFalse(settings.force_all_caps)

    def test_reads_creative_settings_from_payload(self):
        settings = _creative_settings(
            {
                "creative_audio_folder": '"C:\\audios"',
                "input_folder": '"C:\\takes"',
                "output_folder": '"C:\\saida"',
                "creative_broll_path": '"C:\\broll\\produto.mp4"',
                "creative_keywords": "dinâmica, dinamica, dinâmicas",
                "creative_segment_duration": "2.5",
                "creative_trim_audio_edges": True,
                "creative_cut_internal_silence": True,
                "creative_silence_threshold_db": "-34",
                "creative_min_silence_duration": "0.45",
                "creative_keep_silence": "0.18",
                "creative_background_speed": "1.15",
                "creative_speed_broll": True,
            }
        )

        self.assertEqual(str(settings["audio_folder"]), "C:\\audios")
        self.assertEqual(str(settings["takes_folder"]), "C:\\takes")
        self.assertEqual(str(settings["output_folder"]), "C:\\saida")
        self.assertEqual(str(settings["broll_path"]), "C:\\broll\\produto.mp4")
        self.assertEqual(settings["keyword_variants"], ["dinâmica", "dinamica", "dinâmicas"])
        self.assertEqual(settings["segment_duration"], 2.5)
        self.assertTrue(settings["audio_edit_settings"].trim_edges)
        self.assertTrue(settings["audio_edit_settings"].cut_internal_silence)
        self.assertEqual(settings["audio_edit_settings"].silence_threshold_db, -34)
        self.assertEqual(settings["audio_edit_settings"].min_silence_duration, 0.45)
        self.assertEqual(settings["audio_edit_settings"].keep_silence, 0.18)
        self.assertEqual(settings["background_speed"], 1.15)
        self.assertTrue(settings["speed_broll"])


if __name__ == "__main__":
    unittest.main()
