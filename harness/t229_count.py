"""T-0229 の数え直し：docs/ の data-alts から、スマホで顔 32px 未満（emblem_face.unreached）の全身の小元素を数える。
使い方：python harness/t229_count.py（リポジトリの根から。UTF-8 で。PYTHONIOENCODING=utf-8）。基準（合併前）は 35 枚・36 人。目標 10 以下。"""
import re,json,html,sys,glob,os,pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0,str(ROOT/"scripts"))
import emblem_face as ef
rows=[];seen=set()
for f in glob.glob('docs/**/index.html',recursive=True)+glob.glob('docs/*.html'):
    s=open(f,encoding='utf-8').read()
    for m in re.finditer(r'<section[^>]*class="[^"]*sec[^"]*"[^>]*>',s): pass
    for m in re.finditer(r'data-alts="([^"]*)"',s):
        try: alts=json.loads(html.unescape(m.group(1)))
        except Exception: continue
        key=m.group(1)
        if key in seen: continue
        seen.add(key)
        for a in alts:
            if a.get('shape')=='cutout': rows.append((f,a))
print(len(rows),rows[0][1] if rows else None)
by={}
for f,a in rows:
    if a.get('body') or a.get('m'):
        by.setdefault(f,[]).append((a.get('name') or a['src'],{"fs":a.get('bf') or a.get('fs'),"body":a.get('body'),"m":a.get('m'),"fa":a.get('fa'),"ft":a.get('bt')}))
tot=0;miss=[]
for f,l in by.items():
    tot+=len(l); miss+=[(f,)+x for x in ef.unreached(l,'phone')]
print(tot,len(miss))
for m in miss: print(m)
