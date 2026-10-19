"""test1（2026-10-19 までの版）を凍結した写しにする（1 回だけ使った道具。もう一度流しても同じ結果）。

docs/test1/*.html の <head> に読み取り専用の仕掛けを入れる：
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
      if(m!=='GET'&&ok.indexOf(fn)<0){alert('test1 はアーカイブです（見るだけ）。変更は test2 でどうぞ。');
        return Promise.resolve(new Response('{}',{status:403}));}
    }
    return f.apply(this,arguments);
  };
  document.addEventListener('DOMContentLoaded',function(){var d=document.createElement('div');d.className='wl-arch';
    d.innerHTML='アーカイブ：test1（2026-10-19 で更新停止・見るだけ）　<a href="../test2/">いまの版 test2 へ →</a>';document.body.appendChild(d);});
})();</script>
""" % str(READ_OK).replace("'", '"')


def main():
    for p in sorted((ROOT / "docs" / "test1").glob("*.html")):
        t = p.read_text(encoding="utf-8")
        if MARK in t:
            continue
        i = t.find("<head>")
        if i < 0:
            continue
        p.write_text(t[:i + 6] + "\n" + SNIPPET + t[i + 6:], encoding="utf-8")
        print("frozen", p.name)


if __name__ == "__main__":
    main()
