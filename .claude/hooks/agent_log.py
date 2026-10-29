"""会話の動きを 1 行ずつ記録する hook（BACKLOG「全部の会話が何をしているかを記録して見る」）。

SessionStart・PostToolUse・Stop・SubagentStop から呼ばれる。道具の入力はそのまま書かず、
道具の名前・短い要約（ファイル名・命令の最初の語・長さ）だけ。メール・鍵らしい字は消す。
置き場は .claude/agent_log/日付.jsonl（git に入れない）。失敗しても会話は止めない。
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRET = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+|eyJ[\w-]{10,}\.[\w-]+\.[\w-]+|sb_(?:secret|publishable)_\w+|"
    r"(?:ghp|gho|ghs|github_pat|sk|xox[a-z])[-_][\w-]{10,}|\b[A-Za-z0-9_-]{32,}\b"
)


def scrub(s):
    return SECRET.sub("[x]", str(s))[:200]


def summarize(tool, inp):
    inp = inp if isinstance(inp, dict) else {}
    p = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
    if p:
        return scrub(f"{os.path.basename(str(p))} ({len(json.dumps(inp, ensure_ascii=False))}字)")
    c = inp.get("command")
    if c:
        return scrub(f"{str(c).split()[0] if str(c).split() else ''} ({len(str(c))}字)")
    return scrub(f"入力 {len(json.dumps(inp, ensure_ascii=False))}字")


def record(d):
    resp = d.get("tool_response")
    ok = None
    if isinstance(resp, dict):
        ok = not (resp.get("is_error") or resp.get("error") or resp.get("interrupted"))
    tool = d.get("tool_name")
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "event": d.get("hook_event_name") or "?",
        "session": hashlib.sha1(str(d.get("session_id", "")).encode()).hexdigest()[:8],
        "label": scrub(os.environ.get("HARNESS_LABEL") or os.path.basename(str(d.get("cwd") or ""))),
        "tool": scrub(tool) if tool else None,
        "summary": summarize(tool, d.get("tool_input")) if tool else None,
        "dur_ms": d.get("duration_ms") if isinstance(d.get("duration_ms"), int) else None,
        "ok": ok,
    }


def main():
    rec = record(json.load(sys.stdin))
    out = ROOT / ".claude" / "agent_log"
    out.mkdir(parents=True, exist_ok=True)
    with (out / (rec["ts"][:10] + ".jsonl")).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
