from pathlib import Path
import unittest

from video_bridge import resolve_mvp_root


class DistributionLayoutTests(unittest.TestCase):
    def test_resolve_mvp_root_uses_repository_sibling(self) -> None:
        hub_root = Path(r"C:\repo\creative_hub")

        self.assertEqual(resolve_mvp_root(hub_root), Path(r"C:\repo\video_edit_mvp"))
