"""生成した網页を手元の http で開き、JS の例外（pageerror）が 0 かを数える。網は 127.0.0.1 だけ（Supabase などよそは止める）。

2026-11-05：#919 で本番の全ページの JS が止まった。文法（harness/js_check.py）だけでなく、開いて動くかも CI で見る。

    python harness/page_errors.py [home/index.html ...]   # docs/ からの相対
"""
import functools
import http.server
import socketserver
import sys
import threading

sys.path.insert(0, __import__("os").path.dirname(__file__))

PAGES = ["home/index.html", "index.html"]


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    s = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def main(argv):
    from playwright.sync_api import sync_playwright
    import browser   # 写真の配信止めと Supabase の写し（test_browser_guard：直接 chromium.launch しない）
    pages = argv or PAGES
    srv = serve("docs")
    base = f"http://127.0.0.1:{srv.server_address[1]}/Wishlist/"
    errs = []
    with sync_playwright() as p:
        b = browser.launch(p)
        for w in (1400, 390):
            ctx = b.new_context(viewport={"width": w, "height": 900})
            # 手元の http だけ通す。/Wishlist/ の頭は Pages の網址なので docs/ に読み替える
            ctx.route("**/*", lambda r: r.continue_(url=r.request.url.replace("/Wishlist/", "/", 1))
                      if r.request.url.startswith(f"http://127.0.0.1:{srv.server_address[1]}/") else r.abort())
            for path in pages:
                pg = ctx.new_page()
                got = []
                pg.on("pageerror", lambda e, got=got: got.append(str(e)[:200]))
                pg.goto(base + path, wait_until="load", timeout=60000)
                pg.wait_for_timeout(1500)
                errs += [(w, path, e) for e in got]
                pg.close()
            ctx.close()
        b.close()
    srv.shutdown()
    for w, path, e in errs:
        print(f"::error::{path}（{w}px）で JS の例外：{e}")
    print(f"JS の例外：{len(pages)} ページ × 2 幅・{len(errs)} 件")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
