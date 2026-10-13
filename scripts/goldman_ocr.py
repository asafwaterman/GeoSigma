import pymupdf, pytesseract, json, sys
from PIL import Image
from multiprocessing import Pool
F='data/sources/pdf/Goldman-M-Electromagnetic-Survey-Coastal-Aquifer-Israel-GII-Rep-904-62-99-2000.pdf'
def ocr(i):
    d=pymupdf.open(F); pix=d[i].get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    im=Image.frombytes('L',(pix.w,pix.h),pix.samples)
    return i+1, pytesseract.image_to_string(im, config='--psm 6')
if __name__=='__main__':
    with Pool(8) as p: res=dict(p.map(ocr, range(133)))
    json.dump(res, open('data/work/goldman/ocr.json','w'), indent=0)
    print(sum('DATA SET' in t for t in res.values()), 'printout pages')
