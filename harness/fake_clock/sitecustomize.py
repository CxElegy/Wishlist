"""偽の時計：time.sleep を最大 0.02 秒に縮める（harness/fake402_check.py が PYTHONPATH に足す。点検の中だけ）。
網が落ちた状態の再試行の待ち（5・10・15 秒、1 秒おき ×回数）で入口が 50〜90 秒かかっていたのを、再試行の回数は変えずに待ちだけ飛ばす。"""
import importlib.util
import os
import sys
import time

_here = os.path.dirname(os.path.abspath(__file__))
for _p in sys.path:      # 元の sitecustomize（環境のもの）があればそれも走らせる
    _f = os.path.join(os.path.abspath(_p or "."), "sitecustomize.py")
    if os.path.dirname(_f) != _here and os.path.exists(_f):
        _s = importlib.util.spec_from_file_location("_orig_sitecustomize", _f)
        _m = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_m)
        break

_real = time.sleep
time.sleep = lambda s: _real(min(s, 0.02))
