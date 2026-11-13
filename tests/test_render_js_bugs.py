"""render.py の JS（Python の文字列）にあった誤りを、ブラウザーなしで node で確かめる（2026-11-13）。
1 規約の箱が「送りすぎです」になっていた  2 wall() が途中で戻ると前の .wemb が残った
3 頭条の縦長の写真の 3 文がコメントに飲まれていた  4 読み込み中の写真を 8 秒で「開けない」にしていた  5 wallReady が load 待ちだけだった"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import render  # noqa: E402


def part(needle):
    """needle を含む *_JS の文字列（ひとつだけ）。"""
    hit = [getattr(render, n) for n in dir(render) if n.endswith("_JS") and isinstance(getattr(render, n), str) and needle in getattr(render, n)]
    assert len(hit) == 1, (needle, len(hit))
    return hit[0]


def cut(src, start, end):
    """start から end の終わりまで（start は 1 か所だけ）。"""
    assert src.count(start) == 1, start
    i = src.index(start)
    j = src.index(end, i) + len(end)
    return src[i:j]


def node(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
    r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


TIMERS = ("let timers=[],now=0;const setTimeout=(f,ms)=>timers.push({f,at:now+ms});"
          "const adv=ms=>{now+=ms;let t;while((t=timers.find(x=>x.at<=now))){timers.splice(timers.indexOf(t),1);t.f()}};")


@unittest.skipUnless(shutil.which("node"), "node がない")
class RenderJsBugs(unittest.TestCase):
    def test_agree_box_says_terms(self):
        s = cut(part("var agreeBox="), "var agreeBox=function(){", "};")
        out = node("const esc=x=>x,TURL='terms.html',L={sayRate:'RATE',sayErr2:'TERMS'};" + s + "console.log(JSON.stringify(agreeBox()))")
        self.assertTrue(out.endswith("TERMS"))
        self.assertNotIn("RATE", out)

    def test_wall_clears_old_gap_emblems_even_on_early_return(self):
        s = part("const wall = () => {")
        head = cut(s, "const wall = () => {", "if (!w) return;") + "};"
        out = node("let removed=0;const document={querySelectorAll:q=>q==='.wemb'?[{remove(){removed++}},{remove(){removed++}}]:[],querySelector:()=>null};"
                   + head + "wall();console.log(JSON.stringify(removed))")
        self.assertEqual(out, 2)

    def _late(self):
        s = cut(part("const late = new IntersectionObserver"), "const late = new IntersectionObserver", "{rootMargin: '200px'});")
        return (TIMERS + "let cb;const IntersectionObserver=function(c){cb=c;this.unobserve=()=>{};this.observe=()=>{}};"
                "let errs=0;const img={isConnected:true,complete:false,naturalWidth:0,dataset:{e:'1'},dispatchEvent(){errs++}};const Event=function(){};"
                "const window={IntersectionObserver};"
                + s + "\ncb([{isIntersecting:true,target:img}]);")

    def test_slow_photo_is_not_dead(self):
        out = node(self._late() + "adv(8000);adv(5000);adv(5000);console.log(JSON.stringify(errs))")
        self.assertEqual(out, 0)   # まだ読み込み中

    def test_broken_photo_still_falls_back(self):
        out = node(self._late() + "adv(8000);img.complete=true;adv(5000);console.log(JSON.stringify(errs))")
        self.assertEqual(out, 1)   # 読み込み終わり（失敗）→ 代わりの写真へ

    def test_stuck_photo_gives_up_eventually(self):
        out = node(self._late() + "for(let i=0;i<20;i++)adv(5000);console.log(JSON.stringify(errs))")
        self.assertEqual(out, 1)

    def test_wall_ready_has_time_bound(self):
        s = cut(part("let wallReady ="), "let wallReady =", "wallSoon(); } }, 6000);")
        pre = TIMERS + "let soon=0;const wallSoon=()=>soon++;const document={readyState:'loading'};const addEventListener=()=>{};"
        out = node(pre + s + "\nadv(5999);const a=wallReady;adv(2);console.log(JSON.stringify([a,wallReady,soon]))")
        self.assertEqual(out, [False, True, 1])

    def test_lead_portrait_photo_statements_run(self):
        # 頭条の縦長の写真：枠の形・fill・objectPosition の 3 文が、直前のコメントに飲まれていた（2026-11-13）
        s = cut(part("頭条のポスター"), "if (!ok && r0 < 1 && innerWidth > 760) {", "img.style.objectPosition = '';")
        pre = ("const p={style:{},classList:{s:new Set(),add(c){this.s.add(c)}}};const img={style:{objectPosition:'x'}};"
               "const window={},ok=false,r0=.7,innerWidth=1200,innerHeight=800,w0=400,h0=300,nat=.7,top={},fr=null,trimFit=()=>{};")
        out = node(pre + s + "\n}\nconsole.log(JSON.stringify([p.style.aspectRatio,p.classList.s.has('fill'),img.style.objectPosition]))")
        self.assertEqual(out, ["0.7000", True, ""])


if __name__ == "__main__":
    unittest.main()
