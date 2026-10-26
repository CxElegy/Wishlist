import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import emblem_rules as er


class Sparse(unittest.TestCase):
    def test_sparse(self):
        its = [{"name": "a", "emblem_category": "X", "emblem_max": 3}, {"name": "b", "emblem_max": 2},
               {"name": "c", "emblem_max": 1}, {"name": "d", "emblem_who": [], "emblem_max": 1}]
        r = er.sparse_keys(its)
        self.assertEqual([(k, h) for k, h, *_ in r], [("emblem_category", 1)])   # who は空＝なし、max は 4/4 で除く
        self.assertEqual(r[0][3], ["a"])


if __name__ == "__main__":
    unittest.main()
