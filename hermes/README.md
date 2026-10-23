# Hermes agent でハーネスを回す（2026-10-24，用户定的：案 B = 作る係も Hermes に）

[Hermes agent](https://hermes-agent.nousresearch.com/docs/)（Nous Research のオープンソースのエージェント）が、
Claude のループと同じ決まり（`HARNESS.md`）で BACKLOG.md の段を 1 時間に 1 つ進める。止まらない場所（サーバー・PC）で動くので、会話が中断しても止まらない。

## 作る係は 1 つだけ

- `hermes/ACTIVE` が main にある間は **Hermes が作る係**。Claude のループ（harness-forever）は段を取らず、見張りだけ。
- 無い間は Claude のループが作る係で、Hermes は待機（`wishlist-harness` スキルの手順 2）。
- 切り替えは `hermes/ACTIVE` を足す・消す PR 1 つ。同じ段を 2 つの係が取らないよう、段を取るときは BACKLOG を `[~]` にして先に合併する。

## 入れ方

1. 動かす場所に Hermes を入れる（Linux・macOS・WSL2）：
   `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
   （Windows・Mac は公式の Hermes Desktop でもよい。Android は Termux の手順）
2. リポジトリを置く：`git clone https://github.com/CxElegy/Wishlist.git ~/Wishlist && cd ~/Wishlist && pip install -r requirements.txt`
   画面の確かめ用に `pip install playwright && playwright install chromium`、PR 用に GitHub CLI（`gh`）。
3. `~/.hermes/.env` に書く（秘密の値。リポジトリには入れない）：
   - `WISHLIST_DIR=~/Wishlist`
   - モデルの鍵：`ANTHROPIC_API_KEY=…`（または OpenRouter の鍵）
   - `GITHUB_TOKEN=…`（CxElegy/Wishlist に push・PR・合併できるもの。`gh` もこれを使う）
   - `SUPABASE_ACCESS_TOKEN=…`（Supabase の個人トークン。MCP は読むだけで使う）
   - Discord：`DISCORD_BOT_TOKEN=…`、`DISCORD_HOME_CHANNEL=…`（進み具合を送るチャンネル）
4. `hermes/config.example.yaml` の中身を `~/.hermes/config.yaml` に足す（`hermes config edit`）。
5. 定時を作る：
   `hermes cron create "every 1h" "ウォッチリスト通信のハーネスを 1 段進める（wishlist-harness の手順どおり）" --skill wishlist-harness --deliver discord`
6. 作る係を Hermes に：`hermes/ACTIVE` を足す PR を合併する（Claude に「Hermes に切り替えて」と言えば出す）。
7. 確かめ：Discord に「Hermes は待機中」か段の報告が 1 時間ごとに届く。

## 決まり

- 手順・決まりは `skills/wishlist-harness/SKILL.md` と `HARNESS.md`。決まりを変えるときは HARNESS.md を直せば、両方の係に効く。
- データベースの形を変える・消すことはしない（聞く）。お客さまの名前・メールはどこにも書かない。
