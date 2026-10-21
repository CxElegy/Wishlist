"""止めた版を凍結した写しにする（もう一度流しても同じ結果）。

使い方：python scripts/freeze_test1.py [止める版 いまの版 期間]（既定 test1 test2 …）。
2026-10-19 に test1 を止め、2026-10-21 に test1 を店長のページとして戻して test2（試験の版）を止めた。

docs/<止める版>/*.html の <head> に読み取り専用の仕掛けを入れる：
- 画面の下に「アーカイブ」の帯（いまの版 test2 へのリンク）。
- Supabase へ書く呼び出し（依頼・篇幅・投票・写真・今すぐ実行…）は送らずに止める（test2 と同じ表なので、test1 から書くと test2 が変わる）。
  読むもの（投票の読み戻し・依頼の一覧）だけ通す。live_boards（更新中の帯）は test2 の状態なので空で返す。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARK = "<!-- wl-archive -->"
READ_OK = ["my_votes", "list_item_requests", "get_photo_inbox", "instant_enabled", "edit_control_get"]
SNIPPET = MARK + """
<style>.wl-arch{position:fixed;left:0;right:0;bottom:0;z-index:99;padding:6px 16px;background:var(--ink,#1d1d1f);color:var(--paper,#f3efe6);
font:600 12px/1.6 system-ui,sans-serif;text-align:center}.wl-arch a{color:inherit;text-decoration:underline}body{padding-bottom:28px}</style>
<script>(function(){
  var ok=%s, f=window.fetch;
  window.fetch=function(u,o){
    var s=String(u&&u.url||u), m=((o&&o.method)||'GET').toUpperCase(), fn=(s.match(/\\/rpc\\/([a-z_]+)/)||[])[1];
    if(/supabase\\.co/.test(s)){
      if(fn==='live_boards')return Promise.resolve(new Response('[]',{status:200,headers:{'Content-Type':'application/json'}}));
      if(m!=='GET'&&ok.indexOf(fn)<0){alert('__SITE__ はアーカイブです（見るだけ）。');
        return Promise.resolve(new Response('{}',{status:403}));}
    }
    return f.apply(this,arguments);
  };
  document.addEventListener('DOMContentLoaded',function(){var d=document.createElement('div');d.className='wl-arch';
    d.innerHTML='アーカイブ：__SITE__（__WHEN__・見るだけ）　<a href="../__LIVE__/">__LIVE_JA__ →</a>';document.body.appendChild(d);});
})();</script>
""" % str(READ_OK).replace("'", '"')


def main(site="test1", live="test2", when="2026-10-19 で更新停止", live_ja="いまの版 test2 へ"):
    snip = (SNIPPET.replace("__SITE__", site).replace("__LIVE_JA__", live_ja)
            .replace("__LIVE__", live).replace("__WHEN__", when))
    for p in sorted((ROOT / "docs" / site).glob("*.html")):
        t = p.read_text(encoding="utf-8")
        if MARK in t:
            continue
        i = t.find("<head>")
        if i < 0:
            continue
        p.write_text(t[:i + 6] + "\n" + snip + t[i + 6:], encoding="utf-8")
        print("frozen", p.name)


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:5])
