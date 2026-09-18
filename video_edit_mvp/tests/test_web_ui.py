from pathlib import Path
import unittest


class WebUiTests(unittest.TestCase):
    def test_path_fields_have_windows_picker_buttons_and_custom_speed(self):
        html = Path("web/index.html").read_text(encoding="utf-8")

        self.assertIn('data-path-target="creativeAudioFolder"', html)
        self.assertIn('data-path-target="inputFolder"', html)
        self.assertIn('data-path-target="outputFolder"', html)
        self.assertIn('id="creativeBackgroundSpeedCustom"', html)


if __name__ == "__main__":
    unittest.main()
