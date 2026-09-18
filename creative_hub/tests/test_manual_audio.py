from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain import CopyCard, Offer
from manual_audio import import_manual_audio


class ManualAudioImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.offer_root = Path(self.temporary.name) / "kids"
        self.inbox = self.offer_root / "audios_manuais" / "entrada"
        self.library = self.offer_root / "audios_manuais" / "biblioteca"
        self.inbox.mkdir(parents=True)
        self.library.mkdir(parents=True)
        self.offer = Offer(
            id="kids",
            name="Kids",
            slug="kids",
            manual_audio_inbox_folder=str(self.inbox),
            manual_audio_library_folder=str(self.library),
        )
        self.now = datetime(2026, 9, 17, 14, 30)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_import_creates_card_from_filename_and_archives_audio(self) -> None:
        source = self.inbox / "Video 22.wav"
        source.write_bytes(b"audio")

        result = import_manual_audio(self.offer, self.now)

        self.assertFalse(result.empty)
        self.assertEqual(len(result.imported), 1)
        card = result.imported[0]
        self.assertEqual(card.title, "Video 22")
        self.assertEqual(card.audio_source, "manual")
        self.assertEqual(card.status, "audio_ready")
        self.assertTrue(Path(card.audio_path or "").is_file())
        self.assertEqual(Path(card.audio_path or "").parent, self.library / "2026-09-17_1430")
        self.assertFalse(source.exists())

    def test_import_reports_empty_inbox_without_creating_cards(self) -> None:
        result = import_manual_audio(self.offer, self.now)

        self.assertTrue(result.empty)
        self.assertEqual(result.imported, [])
        self.assertEqual(result.skipped, [])
        self.assertFalse((self.library / "2026-09-17_1430").exists())

    def test_import_skips_an_audio_already_linked_to_a_card(self) -> None:
        source = self.inbox / "Video 22.wav"
        source.write_bytes(b"audio")
        archived = self.library / "2026-09-17_1430" / source.name
        self.offer.copies.append(CopyCard(id="existing", title="Video 22", audio_path=str(archived), audio_source="manual"))

        result = import_manual_audio(self.offer, self.now)

        self.assertEqual(result.imported, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn(source.name, result.skipped[0])
        self.assertTrue(source.exists())

    def test_import_rejects_missing_offer_paths(self) -> None:
        invalid_offer = Offer(id="invalid", name="Invalid", slug="invalid")

        with self.assertRaisesRegex(ValueError, "entrada"):
            import_manual_audio(invalid_offer, self.now)

