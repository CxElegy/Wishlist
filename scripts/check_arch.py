"""架构图有没有跟着改（CI 的一步，.github/workflows/ci.yml）。

改了程序的逻辑（scripts/*.py、.github/workflows/*.yml），却没改 scripts/processes.py（管理页「全体の構成」的架构图・流程图・
COMPONENTS 里的模型 / 算法 / 规则），这个 PR 就不通过。docs/rules/admin.md「架构图・流程图的规矩」要求逻辑和图一起改，
光靠记不住（2026-10-17 连着两次漏了），所以让 CI 拦。

确实不影响图的改动（修错字、只改注释、纯重构）：在 PR 说明里写一行
    架构图：不用改（理由）
CI 会把理由印出来，照样通过。

    python scripts/check_arch.py origin/main     # 本地：和 main 比
"""
import json
import os
import subprocess
import sys

ARCH_FILE = "scripts/processes.py"
SKIP_TOKEN = "架构图：不用改"
# 这些文件改了不算「改了逻辑」：只是工具、日志、这个检查自己
NOT_LOGIC = {"scripts/runlog.py", "scripts/resources.py", "scripts/check_arch.py", ARCH_FILE}


def is_logic(path):
    if path in NOT_LOGIC:
        return False
    return (path.startswith("scripts/") and path.endswith(".py")) or \
        (path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")))


def changed_files(base):
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if p]


def _load(src):
    ns = {"__name__": "processes_snapshot"}
    exec(compile(src, ARCH_FILE, "exec"), ns)  # processes.py は html / json / re だけを読む
    return ns["PROCESSES"], ns.get("COMPONENTS", {})


def place_info(base):
    """(ファイル → それを files に持つプロセスの id の集まり, 絵が書き換わったプロセスの id の集まり)。
    プロセスが「書き換わった」= 自分の定義、または uses の部品の定義が base と違う。読めなければ None（この検査は飛ばす）。"""
    try:
        old = subprocess.run(["git", "show", f"{base}:{ARCH_FILE}"], capture_output=True, text=True, check=True).stdout
        with open(ARCH_FILE, encoding="utf-8") as f:
            new = f.read()
        (op, oc), (np, nc) = _load(old), _load(new)
    except Exception:
        return None
    dump = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731
    before = {p["id"]: dump(p) for p in op}
    owners, changed = {}, set()
    for p in np:
        for f in p.get("files", []):
            owners.setdefault(f, set()).add(p["id"])
        if before.get(p["id"]) != dump(p) or any(dump(oc.get(u)) != dump(nc.get(u)) for u in p.get("uses", [])):
            changed.add(p["id"])
    return owners, changed


def pr_body():
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return ((json.load(f).get("pull_request") or {}).get("body")) or ""


def misplaced(logic, place):
    """改った逻辑文件のうち、それを files に持つプロセスがあるのに、そのどれの絵も書き換わっていないもの。"""
    owners, changed = place
    return [(p, sorted(owners[p])) for p in logic if owners.get(p) and not (owners[p] & changed)]


def check(files, body="", place=None):
    """返回 (通过吗, 说明)。place = place_info() の結果（書いた場所も見る）。"""
    logic = [p for p in files if is_logic(p)]
    if not logic:
        return True, "没改逻辑文件"
    skip = next((line.strip() for line in body.splitlines() if SKIP_TOKEN in line), None)
    if ARCH_FILE in files:
        bad = misplaced(logic, place) if place and not skip else []
        if bad:
            return False, ("架构图改了，但改了的文件对应的流程（PROCESSES）没改：\n  " +
                           "\n  ".join(f"{p}（写在 {', '.join(ids)} 的 files 里）" for p, ids in bad) +
                           "\n这个变化要写进上面的流程（flow / COMPONENTS），写在别的流程里不算。"
                           f"\n确实不用的话，在 PR 说明里写一行「{SKIP_TOKEN}（理由）」。")
        return True, f"逻辑和架构图一起改了：{', '.join(logic)}"
    if skip:
        return True, f"PR 说明写了不用改图：{skip}"
    return False, ("改了逻辑却没改架构图（" + ARCH_FILE + "）：\n  " + "\n  ".join(logic) +
                   "\n改了的规则 / 算法 / 流程要写进 COMPONENTS 和对应 PROCESSES 的 flow（docs/rules/admin.md「架构图・流程图的规矩」）。"
                   f"\n确实不影响图的话，在 PR 说明里写一行「{SKIP_TOKEN}（理由）」。")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else f"origin/{os.environ.get('GITHUB_BASE_REF') or 'main'}"
    ok, msg = check(changed_files(base), pr_body(), place_info(base))
    print(("✓ " if ok else "✗ ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
