"""把设计稿（*.dc.html）导出成能直接打开的网页：去掉画布外壳，<helmet> 里的样式搬进 <head>。
用法：python export.py design/Workflow.dc.html docs/design/flow.html "关注清单通信 · 流程图"
"""
import re
import sys

src, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(src, encoding="utf-8").read()
helmet = re.search(r"<helmet>(.*?)</helmet>", s, re.S)
body = re.search(r"</helmet>(.*?)</x-dc>", s, re.S) or re.search(r"<x-dc>(.*?)</x-dc>", s, re.S)
page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{helmet.group(1) if helmet else ""}
</head>
<body>
{body.group(1)}
</body>
</html>
"""
open(out, "w", encoding="utf-8").write(page)
print("→", out)
