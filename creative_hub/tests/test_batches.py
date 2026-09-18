from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from batches import build_batch_targets
from domain import Offer


class BatchTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "oferta" / "output"
        self.offer = Offer(id="kids", name="Kids", slug="kids", output_folder=str(self.output))
        self.now = datetime(2026, 9, 17, 14, 30)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_automatic_batch_uses_next_number_per_offer(self) -> None:
        (self.output / "lote-003-2026-09-16_0900").mkdir(parents=True)

        target = build_batch_targets([self.offer], "automatic", {}, self.now)[self.offer.id]

        self.assertEqual(target.name, "lote-004-2026-09-17_1430")
        self.assertEqual(target.output_folder, self.output / target.name)
        self.assertEqual(target.internal_folder, self.root / "oferta" / ".creative_hub")
        self.assertTrue(target.output_folder.is_dir())
        self.assertTrue((target.internal_folder / "jobs" / target.name).is_dir())

    def test_automatic_batch_creates_a_missing_output_root(self) -> None:
        self.assertFalse(self.output.exists())

        target = build_batch_targets([self.offer], "automatic", {}, self.now)[self.offer.id]

        self.assertEqual(target.name, "lote-001-2026-09-17_1430")
        self.assertTrue(target.output_folder.is_dir())

    def test_custom_batch_sanitizes_its_name(self) -> None:
        target = build_batch_targets([self.offer], "custom", {"kids": " Setembro: Kids? "}, self.now)["kids"]

        self.assertEqual(target.name, "Setembro Kids")
        self.assertTrue(target.output_folder.is_dir())

    def test_custom_batch_rejects_an_empty_sanitized_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "nome"):
            build_batch_targets([self.offer], "custom", {"kids": "<>:*?"}, self.now)

    def test_custom_batch_rejects_windows_reserved_components_with_extensions(self) -> None:
        for reserved_name in ("CON", "prn.txt", "AUX.mp4", "nul.json", "COM1", "com9.log", "LPT1", "lpt9.tmp"):
            with self.subTest(reserved_name=reserved_name):
                with self.assertRaisesRegex(ValueError, "reservado"):
                    build_batch_targets([self.offer], "custom", {"kids": reserved_name}, self.now)

    def test_custom_batch_rejects_an_existing_lot_folder(self) -> None:
        existing = self.output / "setembro"
        existing.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "ja existe"):
            build_batch_targets([self.offer], "custom", {"kids": "setembro"}, self.now)

    def test_custom_batch_rejects_the_same_destination_for_two_offers(self) -> None:
        other_offer = Offer(id="music", name="Music", slug="music", output_folder=str(self.output))

        with self.assertRaisesRegex(ValueError, "mesma pasta"):
            build_batch_targets(
                [self.offer, other_offer],
                "custom",
                {"kids": "setembro", "music": "setembro"},
                self.now,
            )

        self.assertFalse((self.output / "setembro").exists())
