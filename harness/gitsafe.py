"""試験・ハーネスから git を呼ぶときの安全な入口（HARNESS_V2.md「ハーネス v3」D）。

過去に、試験の git が hook から受け継いだ GIT_DIR / GIT_WORK_TREE で本物のリポジトリを書き換えかけた。
  clean_env()        GIT_* を全部外した環境変数
  guard(cwd)         cwd が本物のリポジトリ（このファイルのあるリポジトリ。作業ツリーの本体も）の中・最上位なら AssertionError
  run(cwd, *args)    guard → git を GIT_* なしで流す（user.name/email は固定）。失敗は CalledProcessError
使い方：試験は一時フォルダの中の repo だけを cwd にする。
"""
import os
import pathlib
import subprocess

REAL_ROOT = pathlib.Path(__file__).resolve().parent.parent


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra or {})
    return env


def _git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=clean_env())
    return pathlib.Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None


def toplevel(cwd):
    return _git(cwd, "rev-parse", "--show-toplevel")


def _common_root():
    """作業ツリーでも、本体のリポジトリ（.git のある所）を返す。"""
    p = _git(REAL_ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return p.parent if p else None


def guard(cwd):
    """cwd が本物のリポジトリ（の中）なら止める。git 管理の外・一時フォルダの repo は通す。"""
    c = pathlib.Path(cwd).resolve()
    if c == REAL_ROOT or REAL_ROOT in c.parents:
        raise AssertionError(f"git を本物のリポジトリで流そうとした：{c}（一時フォルダの repo を使う）")
    top = toplevel(c)
    if top is not None and top in (REAL_ROOT, _common_root()):
        raise AssertionError(f"git の最上位が本物のリポジトリ：{top}")


def run(cwd, *args, check=True):
    guard(cwd)
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=clean_env(), check=check)
