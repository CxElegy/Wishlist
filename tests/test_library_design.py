import unittest

import likefx
import library_design as L
import render

OK = {"motif": "magic", "theme": {"bg": "#141B2D", "fg": "#EEF3F8", "accent": "#8FB8E8", "alt_bg": "#EAF1F7", "alt_fg": "#1C2536", "alt_accent": "#4F7CB0"}}


class LibraryDesign(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(L.missing({}), ["motif", "theme"])
        self.assertEqual(L.missing(OK), [])
        self.assertEqual(L.missing({"motif": "pop"}), ["theme"])

    def test_problems(self):
        self.assertEqual(L.problems(OK, render.MOTIFS, likefx.FX), [])
        self.assertTrue(L.problems({**OK, "motif": "nope"}, render.MOTIFS, likefx.FX))
        self.assertTrue(L.problems({**OK, "theme": {**OK["theme"], "bg": "red"}}, render.MOTIFS, likefx.FX))
        self.assertTrue(L.problems({**OK, "like_fx": "nope"}, render.MOTIFS, likefx.FX))


if __name__ == "__main__":
    unittest.main()
