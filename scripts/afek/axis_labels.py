import cv2, numpy as np, glob, hashlib, json
files=sorted(glob.glob("data/work/afekC/p*.png"))
def xticks(d):
    xt=[x for x in range(456,664) if d[461:465,x].sum()>=3]
    t=[]
    for x in xt:
        if t and x-t[-1][-1]<=1: t[-1].append(x)
        else: t.append([x])
    return [453.5]+[float(np.mean(a)) for a in t]+[665.5]
U={};cnt={};R={}
for f in files:
    d=cv2.cvtColor(cv2.imread(f),cv2.COLOR_BGR2GRAY)<128
    ts=xticks(d); ks=[]
    for t in [ts[0],ts[-1]]:
        x=int(round(t)); sub=d[468:476, x+1:x+6]
        k=hashlib.md5(sub.tobytes()).hexdigest()[:8]; U.setdefault(k,sub); cnt[k]=cnt.get(k,0)+1; ks.append(k)
    R[f]={"xticks":ts,"sup":ks}
keys=list(U)
tiles=[]
for i,k in enumerate(keys):
    s=255-(U[k]*255).astype(np.uint8); s=cv2.resize(s,None,fx=10,fy=10,interpolation=cv2.INTER_NEAREST)
    c=np.full((100,110),255,np.uint8); h,w=s.shape; c[10:10+h,50:50+w]=s
    cv2.putText(c,str(i),(2,40),cv2.FONT_HERSHEY_SIMPLEX,0.5,0,1); cv2.putText(c,str(cnt[k]),(2,85),cv2.FONT_HERSHEY_SIMPLEX,0.4,0,1); tiles.append(c)
cols=8; blank=np.full((100,110),255,np.uint8)
rows=[np.hstack(tiles[i:i+cols]+[blank]*(cols-len(tiles[i:i+cols]))) for i in range(0,len(tiles),cols)]
cv2.imwrite("data/work/sup_mosaic.png",np.vstack(rows))
json.dump({"keys":keys,"R":R},open("data/work/sup.json","w"))
print(len(keys))
