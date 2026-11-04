"""run_id ごとに新しいキーで保存する cache は 10 GB の枠を共有して食い切る（2026-11-04：photo cache が 30 回中 6 回「Unable to reserve cache」で赤）。
全 workflow で数える：run_id を含むキーで保存する（actions/cache か cache/save）名前は、photo_cache.yml の掃除の対象に入っていること。"""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def saved_prefixes():
    out = {}
    for f in sorted(WF.glob("*.yml")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"uses:\s*actions/cache(/save)?@v\d+\s*\n(?:.*\n)*?\s*key:[ \t]*(.+)", t):
            key = m.group(2)
            if "run_id" in key:
                out.setdefault(key.split("${{")[0], []).append(f.name)
    return out


class CacheKeysPruned(unittest.TestCase):
    def test_found_the_known_run_id_keys(self):
        p = saved_prefixes()
        for want in ("wl-photo-cache-", "ask-state-", "wishlist-http-", "wd-facts-"):
            self.assertIn(want, p)

    def test_every_run_id_key_is_pruned(self):
        t = (WF / "photo_cache.yml").read_text(encoding="utf-8")
        loop = re.search(r"for p in ([^;]+); do", t).group(1).split()
        for prefix, files in saved_prefixes().items():
            self.assertIn(prefix, loop, f"{files} が run_id キー {prefix} で保存するが photo_cache.yml の掃除に無い")

    def test_prune_runs_always_and_does_not_hide_errors(self):
        t = (WF / "photo_cache.yml").read_text(encoding="utf-8")
        i = t.index("gh cache delete")
        self.assertLess(i, t.index("actions/cache/save@v4"))
        self.assertIn("::warning::gh cache list が失敗", t)
        self.assertNotIn("|| true", t[t.index("古い cache を各名前"):t.index("actions/cache/save@v4")])
        self.assertIn("actions: write", t)

    def test_save_denied_in_workflow_run_redispatches_not_red(self):
        """掃除のあとでも workflow_run の回だけ 'token has no writable scopes' で保存が拒まれた（run 127）。dispatch の回は保存できた（run 128）→ workflow_run の回は dispatch で起こし直し、dispatch の回が入らなければ赤（輪にならない）。"""
        t = (WF / "photo_cache.yml").read_text(encoding="utf-8")
        i = t.index("写しが保存できたか")
        tail = t[i:]
        self.assertIn('= "workflow_dispatch"', tail)
        self.assertIn("exit 1", tail)
        self.assertIn("gh workflow run photo_cache.yml", tail)
        self.assertIn("cache-hit == 'true'", tail.split("Pages を出し直す")[1])


if __name__ == "__main__":
    unittest.main()
