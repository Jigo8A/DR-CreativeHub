from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain import Offer
from offers import ensure_offer_directories, unique_offer_slug


class OfferPathTests(unittest.TestCase):
    def test_offer_directories_are_created_in_the_central_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            offer = Offer(id="kids", name="Kids", slug="kids")

            paths = ensure_offer_directories(root, offer)

            self.assertEqual(paths.takes_folder, str(root / "kids" / "takes"))
            self.assertTrue(Path(paths.output_folder).is_dir())
            self.assertTrue(Path(paths.audio_folder).is_dir())

    def test_new_offer_binds_api_and_manual_audio_directories(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            offer = ensure_offer_directories(root, Offer(id="kids", name="Kids", slug="kids"))

            self.assertEqual(Path(offer.api_audio_folder), root / "kids" / "audios_api")
            self.assertEqual(Path(offer.manual_audio_inbox_folder), root / "kids" / "audios_manuais" / "entrada")
            self.assertEqual(Path(offer.manual_audio_library_folder), root / "kids" / "audios_manuais" / "biblioteca")
            self.assertTrue(Path(offer.api_audio_folder).is_dir())
            self.assertTrue(Path(offer.manual_audio_inbox_folder).is_dir())
            self.assertTrue(Path(offer.manual_audio_library_folder).is_dir())
            self.assertTrue((root / "kids" / ".creative_hub" / "transcricoes").is_dir())
            self.assertTrue((root / "kids" / ".creative_hub" / "jobs").is_dir())

    def test_offer_slug_is_unique_and_windows_safe(self) -> None:
        self.assertEqual(unique_offer_slug("250 Dinamicas: Kids", {"250-dinamicas-kids"}), "250-dinamicas-kids-2")

    def test_configured_folder_is_used_directly_as_the_central_root(self) -> None:
        with TemporaryDirectory() as directory:
            central_root = Path(directory) / "ofertas"
            offer = Offer(id="kids", name="Kids", slug="kids")

            paths = ensure_offer_directories(central_root, offer)

            self.assertEqual(paths.output_folder, str(central_root / "kids" / "output"))
            self.assertFalse((central_root / "ofertas").exists())
