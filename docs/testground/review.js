/* 審査の見本に共通の「答える」欄（HARNESS「審査の見本は触って決める」）。
   <script src="review.js" data-page data-why data-now data-change data-options="A=…|B=…"></script> を置くと、
   ページの先頭に なぜ聞くか／今どうなっているか／選ぶと何が変わるか の 3 行、下に押して選ぶ欄と「答えを保存」。
   保存先は review_save（店長ログイン→review_answers）。ログインがなくてもこのブラウザには残る。 */
(function () {
  var s = document.currentScript, d = s.dataset, page = d.page, K = "rv-" + page;
  var U = "https://bzokpnbcjscbcehdxtjq.supabase.co", KEY = "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC";
  var opts = (d.options || "").split("|").map(function (o) { var i = o.indexOf("="); return [o.slice(0, i), o.slice(i + 1)]; });
  var st = { choice: "", note: "" };
  try { st = JSON.parse(localStorage.getItem(K) || "{}") || st; } catch (e) {}
  function esc(x) { return String(x).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  var css = document.createElement("style");
  css.textContent = ".rv3,.rvf{font:500 14px/1.7 'Noto Sans JP',sans-serif;color:#1A1C22;background:#FBF8F1;border:2px solid #1A1C22;box-shadow:4px 4px 0 #1A1C22;margin:12px auto;max-width:1100px;padding:12px 16px;box-sizing:border-box}" +
    ".rv3{width:calc(100% - 24px)}.rvf{width:calc(100% - 24px)}@media(min-width:700px){.rvf{position:sticky;bottom:8px;z-index:50}}.rv3 dl{margin:0}.rv3 dt{font-weight:900;display:inline-block;background:#FFD23F;padding:0 8px;margin-right:6px}.rv3 dd{display:inline;margin:0}.rv3 div{margin:4px 0}" +
    ".rvf b{margin-right:8px}.rvf button{font:700 14px 'Noto Sans JP',sans-serif;min-height:44px;padding:6px 14px;margin:3px 6px 3px 0;border:2px solid #1A1C22;background:#fff;color:#1A1C22;cursor:pointer}" +
    ".rvf button[aria-pressed=true]{background:#1A1C22;color:#FFD23F}.rvf textarea{width:100%;min-height:44px;font:500 14px 'Noto Sans JP',sans-serif;border:2px solid #1A1C22;padding:6px;box-sizing:border-box;margin-top:6px}" +
    ".rvf .go{background:#B8336A;color:#fff}.rvf .msg{display:block;margin-top:6px;font-size:13px}";
  document.head.appendChild(css);
  var top = document.createElement("section");
  top.className = "rv3"; top.id = "rv-why";
  top.innerHTML = "<dl><div><dt>なぜ聞くか</dt><dd>" + esc(d.why) + "</dd></div><div><dt>今は</dt><dd>" + esc(d.now) + "</dd></div><div><dt>選ぶと</dt><dd>" + esc(d.change) + "</dd></div></dl>";
  var f = document.createElement("section");
  f.className = "rvf"; f.id = "rv-answer";
  f.innerHTML = "<b>あなたの答え</b>" + opts.map(function (o) { return '<button type="button" data-c="' + esc(o[0]) + '" aria-pressed="false">' + esc(o[0]) + "　" + esc(o[1]) + "</button>"; }).join("") +
    '<textarea placeholder="気になったところ（任意）" aria-label="気になったところ"></textarea><button type="button" class="go">答えを保存</button><span class="msg" role="status"></span>';
  var b = document.body, h = b.querySelector("header");
  if (h && h.parentNode) h.parentNode.insertBefore(top, h.nextSibling); else b.insertBefore(top, b.firstChild);
  b.appendChild(f);
  var ta = f.querySelector("textarea"), msg = f.querySelector(".msg");
  ta.value = st.note || "";
  function paint() { f.querySelectorAll("button[data-c]").forEach(function (x) { x.setAttribute("aria-pressed", x.dataset.c === st.choice); }); }
  function keep() { try { localStorage.setItem(K, JSON.stringify(st)); } catch (e) {} }
  paint();
  f.addEventListener("click", function (e) {
    var c = e.target.closest("button[data-c]");
    if (c) { st.choice = c.dataset.c; keep(); paint(); return; }
    if (!e.target.closest(".go")) return;
    st.note = ta.value; keep();
    if (!st.choice) { msg.textContent = "先に A・B などを 1 つ押してください。"; return; }
    var tok = ""; try { tok = (JSON.parse(localStorage.getItem("wl-auth") || "{}") || {}).access_token || ""; } catch (x) {}
    msg.textContent = "このブラウザには保存しました。";
    if (!tok) { msg.textContent += "　係に届けるには本番のページ（右上のログイン）で店長でログインしてから、もう一度押してください。"; return; }
    fetch(U + "/rest/v1/rpc/review_save", { method: "POST", headers: { apikey: KEY, Authorization: "Bearer " + tok, "Content-Type": "application/json" },
      body: JSON.stringify({ p_page: page, p_step: "1", p_answer: { choice: st.choice, note: st.note } }) })
      .then(function (r) { return r.text().then(function (t) { if (!r.ok) throw new Error(t.slice(0, 120)); msg.textContent = "保存しました。係に届きました。"; }); })
      .catch(function (err) { msg.textContent += "　届けられませんでした：" + err.message; });
  });
})();
