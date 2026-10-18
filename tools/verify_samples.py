"""Optional publication preflight; only samples/fictional.csv is read."""
from pathlib import Path
import json
import math
import sys
from PIL import Image
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader
import zxingcpp

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from event_cards import ASSEMBLY_COPY,ASSEMBLY_EXAMPLE,read_cards,tweet_intent
folder=ROOT/"samples";cards=read_cards(folder/"fictional.csv")
normalize=lambda text:''.join(text.split())
pt=lambda n:n*72/25.4
report=[]
for template,filename in [('tent','tent-cards.pdf'),('badges','neck-badges.pdf')]:
    path=folder/filename;reader=PdfReader(path);raster=pdfium.PdfDocument(path)
    assert len(reader.pages)==(len(cards) if template=='tent' else math.ceil(sum(c.participant_count for c in cards)/8))
    previews=[]
    for i,page in enumerate(reader.pages):
        assert abs(float(page.mediabox.width)-pt(210))<.01 and abs(float(page.mediabox.height)-pt(297))<.01
        assert not page.get('/Annots')
        text=page.extract_text();assert '\ufffd' not in text
        fonts=page['/Resources']['/Font'].get_object()
        embedded=[]
        for ref in fonts.values():
            font=ref.get_object()
            if '/FontDescriptor' in font:
                descriptor=font['/FontDescriptor'].get_object()
                assert '/FontFile2' in descriptor and descriptor['/FontFile2'].get_object().get_data()
                embedded.append(font.get('/BaseFont'))
        assert embedded
        if template=='tent':
            card=cards[i]
            for value in [card.name,card.title,card.description,card.place,*ASSEMBLY_COPY]:assert normalize(value) in normalize(text)
            for value in [*ASSEMBLY_EXAMPLE,"紙の下端","折り返し"]:assert normalize(value) in normalize(text)
            assert '根元まで21mm' not in text
            # Inspect real PDF stroke coordinates, including transformed diagrams.
            paths=[];points=[]
            def visitor(op,args,cm,tm):
                global points
                if op==b'm':points=[]
                if op in [b'm',b'l']:
                    x,y=map(float,args);points.append((cm[0]*x+cm[2]*y+cm[4],cm[1]*x+cm[3]*y+cm[5]))
                if op==b'S' and len(points)==2:paths.append(points[:]);points=[]
            page.extract_text(visitor_operand_before=visitor)
            horizontal=[p for p in paths if abs(p[0][1]-p[1][1])<.01 and abs(abs(p[0][0]-p[1][0])-pt(198))<.01]
            assert len(horizontal)==3
            assert all(any(abs(p[0][1]-pt(297-v))<.01 for p in horizontal) for v in [21,113,205])
            cuts=[p for p in paths if abs(p[0][0]-p[1][0])<.01 and abs(p[0][1]-pt(291))<.01 and abs(p[1][1]-pt(276))<.01]
            assert len(cuts)==5
        for dpi in [150,300]:
            image=raster[i].render(scale=dpi/72).to_pil().convert('RGB')
            a=np.asarray(image);margin=round(5.8/25.4*dpi)
            assert all(np.all(edge==255) for edge in [a[:margin],a[-margin:],a[:,:margin],a[:,-margin:]])
            codes=zxingcpp.read_barcodes(image)
            if template=='tent':
                assert len(codes)==1 and codes[0].text==tweet_intent(cards[i].title,cards[i].name,cards[i].x_profile)
                assert np.all(a[round(21.2/25.4*dpi):round(112.8/25.4*dpi)]==255)
                assert np.all(a[round(276.2/25.4*dpi):]==255)
                band=a[:round(21/25.4*dpi)]
                red=(band[:,:,0]>150)&(band[:,:,1]<60)&(band[:,:,2]<60)
                for col,center in enumerate([28.35,63.35,96.05,133.35,168.35,201.05]):
                    left,right=round(col*35/25.4*dpi),round((col+1)*35/25.4*dpi)
                    ys,xs=np.nonzero(red[:,left:right])
                    assert len(xs)>150 and abs((xs.min()+xs.max())/2+left-center/25.4*dpi)<2
                    width=(xs.max()-xs.min()+1)/dpi*25.4
                    # At 150dpi the diagonal's antialiased end pixels may fall
                    # below the solid-red threshold; allow one pixel per end.
                    assert (5.6<width<6.3 if col<3 else 4.5<width<5.5),(dpi,col,width)
            else:assert not codes
            if dpi==150:
                previews.append(image)
                if template=='tent' and i==0:
                    crop=image.crop((0,round(113/25.4*dpi),image.width,round(205/25.4*dpi))).rotate(180)
                    crop.save(folder/'assembly-preview.png')
        report.append({'file':filename,'page':i+1,'a4':True,'japanese_font_embedded':True,'margin_mm':6,'qr_150_300dpi':template=='tent'})
    preview=Image.new('RGB',(sum(im.width for im in previews),max(im.height for im in previews)),'white')
    x=0
    for image in previews:preview.paste(image,(x,0));x+=image.width
    preview.save(folder/filename.replace('.pdf','.png'))
    if template=='badges':
        all_text=normalize(''.join(page.extract_text() for page in reader.pages))
        for card in cards:assert all_text.count(normalize(card.name))==card.participant_count
        for i,page in enumerate(reader.pages):
            for position in range(8):
                x=6+(position%2)*99;y=6+(position//2)*71.25
                if i*8+position>=sum(c.participant_count for c in cards):
                    # Blank tail cells have no text glyphs.
                    textpage=raster[i].get_textpage();assert not textpage.get_text_bounded(left=pt(x),bottom=pt(297-y-71.25),right=pt(x+99),top=pt(297-y)).strip()
(ROOT/'.local').mkdir(exist_ok=True)
(ROOT/'.local'/'sample-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Verified fictional vector PDFs, Japanese embedding, exact two-sentence copy, real folds/cuts, 150/300dpi QR, margins, nine badges and blank tail cells.')
