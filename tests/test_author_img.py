import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import images  # noqa: E402


class AuthorImg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        images.AUTHOR_FILE = pathlib.Path(self.tmp.name) / "a.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_yoast_person_image_is_dropped_and_remembered(self):
        who = "https://cdn.x.net/uploads/100_0578-scaled.jpg"
        ld = {"@graph": [{"@type": "Article", "image": {"@id": "#primary"}, "author": {"@id": "#a"}},
                         {"@type": "ImageObject", "url": "https://cdn.x.net/uploads/Logo.jpg"},
                         {"@type": "Person", "@id": "#a", "image": {"@type": "ImageObject", "@id": "#authorImage", "url": who}}]}
        html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        p = images.parse_page("https://x.net/a/", html)
        self.assertNotIn(who, p.jsonld)
        self.assertIn(who, images.author_seen())

    def test_gravatar_in_jsonld_is_dropped(self):
        ld = {"@graph": [{"author": {"image": "https://secure.gravatar.com/avatar/c590?s=96&d=retro"}},
                         {"image": "https://noisypixel.net/wp-content/uploads/2026/10/bleach-scaled.jpg"}]}
        html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        p = images.parse_page("https://noisypixel.net/a/", html)
        self.assertEqual(p.jsonld, ["https://noisypixel.net/wp-content/uploads/2026/10/bleach-scaled.jpg"])

    def test_og_avatar_dropped_normal_kept(self):
        html = ('<meta property="og:image" content="https://x.com/wp-content/uploads/avatars/me.jpg">'
                '<meta property="og:image" content="https://x.com/uploads/2026/10/cover.jpg">')
        p = images.parse_page("https://x.com/a/", html)
        self.assertEqual(p.og, ["https://x.com/uploads/2026/10/cover.jpg"])


if __name__ == "__main__":
    unittest.main()
