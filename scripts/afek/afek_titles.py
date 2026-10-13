import cv2, pytesseract, pymupdf, re, json
d=pymupdf.open("data/sources/pdf/Afek-Project-Geophysical-Report-Appendix-C.pdf")
out=[]
for pno in range(2,len(d)):
    p=d[pno]; imgs=p.get_images(full=True)
    items=[]
    for i,img in enumerate(imgs):
        r=p.get_image_rects(img[0])[0]; items.append((r.y0,i))
    for y,i in sorted(items):
        f=f"data/work/afekC/p{pno+1:03d}_{i}.png"
        g=cv2.cvtColor(cv2.imread(f),cv2.COLOR_BGR2GRAY)[16:30,48:330]
        big=cv2.resize(g,None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST)
        _,big=cv2.threshold(big,150,255,cv2.THRESH_BINARY); big=cv2.GaussianBlur(big,(3,3),0)
        big=cv2.copyMakeBorder(big,30,30,30,30,cv2.BORDER_CONSTANT,value=255)
        t=pytesseract.image_to_string(big,config="--psm 7").strip()
        m=re.search(r"Line\s+(\S+?)\.?\s+Stat\S*\s+(\S+)",t,re.I)
        out.append({"file":f,"page":pno+1,"title":t,"line_ocr":m.group(1) if m else None,"stn_ocr":m.group(2) if m else None})
json.dump(out,open("data/work/afek_titles.json","w"),indent=0)
for o in out: print(o["page"],o["line_ocr"],o["stn_ocr"],"|",o["title"][:60])
