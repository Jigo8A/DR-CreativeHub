from pathlib import Path
import unittest

from domain import CopyCard, default_state
from storage import StateStore


class StateStoreTests(unittest.TestCase):
    def test_store_round_trips_copy_and_settings(self) -> None:
        temporary_dir = Path(self._testMethodName)
        self.addCleanup(lambda: None)

        state = default_state()
        state.copies.append(CopyCard(id="copy-a", title="Gancho", text="Texto da copy"))
        state.settings.output_folder = r"C:\saida"

        with self.subTest("state can be stored"):
            store = StateStore(Path.cwd() / ".test-state.json")
            self.addCleanup(lambda: store.path.unlink(missing_ok=True))
            store.save(state)
            restored = store.load()

        self.assertEqual(restored.copies[0].title, "Gancho")
        self.assertEqual(restored.settings.output_folder, r"C:\saida")

    def test_load_uses_defaults_when_state_does_not_exist(self) -> None:
        path = Path.cwd() / ".missing-state.json"
        path.unlink(missing_ok=True)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        state = StateStore(path).load()

        self.assertEqual(state.copies, [])
        self.assertEqual(state.settings.subtitle_mode, "highlight")
