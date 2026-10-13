"""Map the 240 App C plots (page order) to App B receivers.
App C plots run in App B line order, stations ascending within a line (Ey at its
numeric position). App C has no plots for A4 500/700 or line E2-3, and one plot for
P2 (Ex and Ey share one location)."""
import json, re
T=json.load(open("data/work/afek_titles.json"))
R=[l.split() for l in open("data/surveys/afek-2013-csamt/extraction/appB_receivers.txt")]
lines=[]
for r in R:
    if r[0] not in lines: lines.append(r[0])
seq=[]
for ln in lines:
    rows=sorted([r for r in R if r[0]==ln], key=lambda r:(int(r[1]), r[2]))
    for r in rows:
        if ln=="E2-3" or (ln=="A4" and r[1] in("500","700")) or (ln=="P2" and r[2]=="Ey"): continue
        seq.append(r)
assert len(seq)==len(T), (len(seq),len(T))
def tstn(t):
    m=re.search(r"St\S*\s+(\S+)",t["title"],re.I)
    return re.sub(r"\D","",(m.group(1) if m else "").replace("S","5").replace("+","4"))
out=[];bad=0
for t,r in zip(T,seq):
    s=tstn(t); ok = s==r[1] or (len(s)==3 and s[0]==r[1][0]) or (s in("200","190") and r[1] in("100","300","500"))
    if not ok: bad+=1; print("check", t["file"], t["title"][:50], "->", r[:3])
    out.append({"file":t["file"],"page":t["page"],"line":r[0],"station":int(r[1]),"comp":r[2],"x":float(r[3]),"y":float(r[4]),"array":r[6],"title_ocr":t["title"]})
json.dump(out,open("data/work/afek_map.json","w"),indent=0)
print(len(out),"mapped,",bad,"to check")
