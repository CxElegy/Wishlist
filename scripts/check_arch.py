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


def pr_body():
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return ((json.load(f).get("pull_request") or {}).get("body")) or ""


def check(files, body=""):
    """返回 (通过吗, 说明)。"""
    logic = [p for p in files if is_logic(p)]
    if not logic:
        return True, "没改逻辑文件"
    if ARCH_FILE in files:
        return True, f"逻辑和架构图一起改了：{', '.join(logic)}"
    for line in body.splitlines():
        if SKIP_TOKEN in line:
            return True, f"PR 说明写了不用改图：{line.strip()}"
    return False, ("改了逻辑却没改架构图（" + ARCH_FILE + "）：\n  " + "\n  ".join(logic) +
                   "\n改了的规则 / 算法 / 流程要写进 COMPONENTS 和对应 PROCESSES 的 flow（docs/rules/admin.md「架构图・流程图的规矩」）。"
                   f"\n确实不影响图的话，在 PR 说明里写一行「{SKIP_TOKEN}（理由）」。")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else f"origin/{os.environ.get('GITHUB_BASE_REF') or 'main'}"
    ok, msg = check(changed_files(base), pr_body())
    print(("✓ " if ok else "✗ ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
