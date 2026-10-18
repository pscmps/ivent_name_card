"""Local CSV-only, vector A4 tent cards and eight-up neck badges (MIT)."""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

from PIL import Image, ImageOps
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

DEFAULT_FONT = Path(__file__).resolve().parent / "assets" / "NotoSansJP-Regular.ttf"
ASSEMBLY_COPY = (
    "破線を山折りで折り、カメラ、SNS共有、タッチのOK/NGを必要に応じて説明欄の下に出してください",
    "全てOKの場合は真ん中だけ切り左半分を見せればOKです",
)
ASSEMBLY_EXAMPLE = (
    "例)全てOK:中央だけ切る",
    "　※NGがある場合は切れ目を追加し調整",
)
QR_CAPTION = "X(旧Twitter)に感想を簡単に投稿できます！"
JP = "EventCardJP"
BLUE, RED, GREY = (0.1, 0.35, 0.55), (0.65, 0.2, 0.15), (0.65,) * 3


@dataclass(frozen=True)
class Card:
    name: str
    title: str
    description: str
    x_profile: str | None
    place: str = "未割当"
    image: Path | None = None
    participant_count: int | None = None
    csv_line: int = 0


def x_profile(value: str) -> str | None:
    value = value.strip()
    if not value or value.rstrip("/").lower() in ("https://x.com", "http://x.com", "https://twitter.com", "http://twitter.com"):
        return None
    if "://" in value:
        url = urlparse(value)
        if url.scheme not in ("http", "https") or url.hostname not in ("x.com", "twitter.com") or url.username or url.password or url.port:
            raise ValueError("x列はXプロフィールURL、@handle、または空欄にしてください")
        value = url.path.strip("/")
        if not value:
            return None
    value = value.removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", value):
        raise ValueError("x列のアカウント名を確認してください")
    return "https://x.com/" + value


def tweet_intent(title: str, name: str, profile: str | None, hashtag="つくろがや") -> str:
    tag = hashtag.removeprefix("#")
    if not re.fullmatch(r"[^\s#]{1,80}", tag):
        raise ValueError("ハッシュタグは空白なしの1語にしてください")
    params = {"text": f"{title}({name})  #{tag}"}
    if profile:
        params["url"] = profile
    return "https://twitter.com/intent/tweet?" + urlencode(params)


def positive_count(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value.strip()):
        raise ValueError("参加人数は正の整数にしてください")
    count = int(value)
    if not 1 <= count <= 9007199254740991:
        raise ValueError("参加人数は正の安全な整数にしてください")
    return count


def read_cards(path: Path, *, allow_blank_work=False) -> list[Card]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"name", "作品", "作品説明", "x"}.issubset(reader.fieldnames or []):
            raise ValueError("CSVには name,作品,作品説明,x の列が必要です")
        cards = []
        for line, row in enumerate(reader, 2):
            cell = lambda key: (row.get(key) or "").strip(" \t")
            name, title, description = cell("name"), cell("作品"), cell("作品説明")
            if not name and not title and not description:
                continue
            if not name.strip() or len(name) > 30 or (not allow_blank_work and not title.strip()) or len(title) > 100 or len(description) > 100:
                raise ValueError(f"CSV {line}行: 名前1〜30文字、作品1〜100文字、説明100文字以内にしてください")
            raw, alias = cell("参加人数"), cell("participantCount")
            if raw and alias and positive_count(raw) != positive_count(alias):
                raise ValueError(f"CSV {line}行: 参加人数とparticipantCountが一致しません")
            count = positive_count(raw or alias) if raw or alias else None
            place, day = cell("場所"), cell("日付")
            clean_day = re.sub(r"\s*[（(]\s*仮日程\s*[）)]", "", day).replace("仮日程", "").strip()
            place = (clean_day + "  " + (place or "未割当")).strip()
            if cell("画像").startswith(("http:","https:","//","\\\\")):
                raise ValueError("画像はローカルのファイルパスを指定してください")
            image = Path(cell("画像")) if cell("画像") else None
            if image is not None and not image.is_absolute():
                image = path.resolve().parent / image
            cards.append(Card(name, title, description, x_profile(cell("x")), place, image, count, line))
    if not cards:
        raise ValueError("CSVに出力対象がありません")
    return cards


def register_font(path: Path):
    if not path.is_file():
        raise ValueError("日本語TTFが見つかりません。--fontで指定してください")
    pdfmetrics.registerFont(TTFont(JP, str(path)))


def check_glyphs(text: str):
    cmap = pdfmetrics.getFont(JP).face.charToGlyph
    if any(not cmap.get(ord(char)) for char in text if char not in "\r\n"):
        raise ValueError("日本語フォントにない文字があります。入力文字または--fontを確認してください")


def wrapped(text: str, font: str, size: float, width: float) -> list[str]:
    lines = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        current = ""
        for char in paragraph:
            if current and pdfmetrics.stringWidth(current + char, font, size) > width:
                lines.append(current)
                current = ""
            current += char
        lines.append(current)
    return lines


class Drawing:
    """Coordinates in millimetres from the physical paper's top-left."""
    def __init__(self, pdf):
        self.pdf = pdf

    def line(self, x1, top1, x2, top2, *, color=GREY, dashed=False, weight=.4):
        c = self.pdf
        c.saveState()
        c.setStrokeColorRGB(*color)
        c.setLineWidth(weight)
        c.setDash([3, 3] if dashed else [])
        c.line(x1*mm, A4[1]-top1*mm, x2*mm, A4[1]-top2*mm)
        c.restoreState()

    def box(self, text, x, top, width, height, maximum, minimum=8, *, font=JP, centered=False, max_lines=math.inf):
        size = maximum
        while size >= minimum:
            lines = wrapped(text, font, size, width*mm)
            leading = size * 1.25
            if len(lines) <= max_lines and len(lines)*leading <= height*mm:
                c = self.pdf
                c.setFont(font, size)
                c.setFillColorRGB(0, 0, 0)
                inset = (height*mm-len(lines)*leading)/2 if centered else 0
                for i, line in enumerate(lines):
                    xx = x*mm + ((width*mm-pdfmetrics.stringWidth(line, font, size))/2 if centered else 0)
                    c.drawString(xx, A4[1]-top*mm-inset-size-i*leading, line)
                return
            size -= .5
        raise ValueError("文字が印刷範囲に収まりません。名前・作品・説明・場所を確認してください")


def permission_band(d: Drawing):
    c = d.pdf
    for option in range(2):
        for group in range(3):
            left = (option*3+group)*35+6.25
            line = lambda x1, y1, x2, y2: d.line(x1, y1, x2, y2, color=(0, 0, 0), weight=1.4)
            c.saveState()
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(1.4)
            if group == 0:
                c.rect(left*mm, A4[1]-20*mm, 16.5*mm, 10*mm, stroke=1, fill=0)
                line(left+3, 10, left+5, 8)
                line(left+5, 8, left+11.5, 8)
                line(left+11.5, 8, left+13.5, 10)
                c.circle((left+8.25)*mm, A4[1]-15*mm, 3.2*mm, stroke=1, fill=0)
            elif group == 1:
                points = [(0,0),(16.5,0),(16.5,9),(7,9),(3,11),(3,9),(0,9)]
                path = c.beginPath()
                path.moveTo((left+points[0][0])*mm, A4[1]-(9+points[0][1])*mm)
                for xx, yy in points[1:]:
                    path.lineTo((left+xx)*mm, A4[1]-(9+yy)*mm)
                path.close()
                c.drawPath(path, stroke=1, fill=0)
                d.box("SNS",left+2,11,14,6,10,10)
            else:
                hand = [(4,16),(0,10),(1,8),(5,11),(5,2),(7,2),(7,9),(8,0),(10,0),(10,9),(11,1),(13,1),(13,10),(14,3),(16,3),(16,15),(13,20),(7,20),(4,16)]
                for a, b in zip(hand, hand[1:]):
                    line(left+3+a[0]*.7,6.5+a[1]*.7,left+3+b[0]*.7,6.5+b[1]*.7)
            # Equal nominal 3.1mm outline gap for camera, SNS and hand.
            bx, top = left+(19.8 if group == 2 else 22.1), 8.9
            c.setStrokeColorRGB(.82,.03,.05)
            c.setLineWidth(2.6)
            if option == 0:
                c.circle(bx*mm,A4[1]-top*mm,2.5*mm,stroke=1,fill=0)
            else:
                d.line(bx-2.2,top-2.2,bx+2.2,top+2.2,color=(.82,.03,.05),weight=2.6)
                d.line(bx-2.2,top+2.2,bx+2.2,top-2.2,color=(.82,.03,.05),weight=2.6)
            c.restoreState()


def assembly(d: Drawing):
    c = d.pdf
    for x in (35,70,105,140,175):
        d.line(x,6,x,21)
    for top in (21,113,205):
        d.line(6,top,204,top,dashed=True)
    c.saveState()
    c.translate(105*mm,A4[1]-159*mm)
    c.rotate(180)
    c.translate(-105*mm,-(A4[1]-159*mm))
    d.box("組み立て",12,121,186,6,10,10)
    d.box("\n".join(ASSEMBLY_COPY),12,130,186,18,10,10)
    d.box(ASSEMBLY_EXAMPLE[0],12,152,100,5,9,9)
    d.box(ASSEMBLY_EXAMPLE[1],12,158,105,5,9,9)
    c.saveState()
    c.translate(12*mm,A4[1]-167*mm)
    c.scale(.45,.45)
    c.translate(0,-A4[1])
    permission_band(d)
    c.restoreState()
    mark = lambda a,b,x,y,col,weight=1: d.line(a,b,x,y,color=col,weight=weight)
    mark(59.25,167,59.25,176.45,(.82,.03,.05))
    d.line(12,176.45,106.5,176.45,dashed=True)
    for x,col in ((35.6,(.125,.125,.125)),(82.9,(.82,.03,.05))):
        mark(x,178,x,182,col)
        mark(x,182,x-1.2,180.5,col)
        mark(x,182,x+1.2,180.5,col)
    d.box("表へ",29,184,24,5,9,9)
    d.box("裏へ",76,184,24,5,9,9)
    # Approved side view: the selector alternatives share one bottom-right
    # hinge; the front is a separate free end. No extra return or fold.
    d.box("横から見た図",118,151,80,5,9,9)
    k,apex = .074,860-350*math.sqrt(3)
    ink,note,selector_red = (.125,.125,.125),(.408,.408,.408),(.82,.03,.05)
    def point(p):return (118+(p[0]-450)*k,157+(p[1]-apex)*k)
    def path(points,color,width):
        for a,b in zip(points,points[1:]):
            mark(*point(a),*point(b),color,width*k*mm)
    def label(value,x,y,size,color=ink):
        px,py=point((x,y))
        c.setFont(JP,size*k*mm)
        c.setFillColorRGB(*color)
        c.drawString(px*mm,A4[1]-py*mm,value)
    hinge,outside=(1150,860),(1054,615)
    ratio=math.hypot(96,245)/math.hypot(246,93)
    inside=(1150-246*ratio,860-93*ratio)
    path([(1050,860-60*math.sqrt(3)),(800,apex),(450,860),hinge,outside],ink,7.5)
    path([hinge,inside],selector_red,7.5)
    label("前面",1020,425,34)
    path([(1005,438),(922.5,500)],note,2)
    label("外側へ立てる",1240,515,40)
    label("見せるマーク",1240,565,30)
    path([(1240,590),(1190,590),(1092.4,713)],note,2)
    label("内側へ入れる",640,598,40,selector_red)
    label("隠すマーク",640,645,30,selector_red)
    path([(850,666),(960,720),(1002.3,804.2)],note,2)
    c.restoreState()


def photo(path: Path) -> Image.Image:
    if not path.is_file() or path.stat().st_size > 5*1024*1024:
        raise ValueError("画像は存在する5MB以内のPNG/JPEG/WebPを指定してください")
    with Image.open(path) as original:
        if original.format not in ("PNG","JPEG","WEBP") or original.width*original.height > 40_000_000:
            raise ValueError("画像はPNG/JPEG/WebP、4000万画素以内にしてください")
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.info.clear()
    scale = min(1,60/25.4*300/image.width,26/25.4*300/image.height)
    if scale < 1:
        image = image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS)
    return image


def tent_front(d: Drawing, card: Card, hashtag: str):
    c, top = d.pdf,205
    d.box(card.name,10,top+2.5,130,10.5,20,11.5)
    if card.x_profile:
        d.box("@"+card.x_profile.rsplit("/",1)[1],10,top+14,130,4,9)
    d.box(card.title,10,top+19,130,14,16,9.5)
    if card.image:
        image = photo(card.image)
        factor = min(60/image.width,26/image.height)
        w,h = image.width*factor,image.height*factor
        c.drawImage(ImageReader(image),(10+(60-w)/2)*mm,A4[1]-(top+35+26)*mm+(26-h)/2*mm,w*mm,h*mm)
    d.box(card.description,77 if card.image else 10,top+35,60 if card.image else 130,26,10.5 if card.image else 12.5,9)
    place = card.place.replace("・","·").replace("／"," / ")
    latin = all(32 <= ord(ch) <= 126 or ch == "·" for ch in place)
    d.box(place if latin else card.place,10,top+63,130,8,10,6,font="Helvetica" if latin else JP)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=1)
    qr.add_data(tweet_intent(card.title,card.name,card.x_profile,hashtag))
    qr.make(fit=True)
    matrix = qr.get_matrix()
    module = 55/len(matrix)
    if module < .3:
        raise ValueError("QRが細かすぎます。作品名・名前・ハッシュタグを短くしてください")
    c.setFillColorRGB(0,0,0)
    for yy,row in enumerate(matrix):
        for xx,black in enumerate(row):
            if black:
                c.rect((145+xx*module)*mm,A4[1]-(top+3+(yy+1)*module)*mm,module*mm,module*mm,stroke=0,fill=1)
    d.box(QR_CAPTION.replace("簡単に","\n簡単に"),145,top+59,55,8,8.5,8)


def badge_counts(cards: list[Card], default_count: int | None) -> list[int]:
    result = []
    for card in cards:
        count = card.participant_count if card.participant_count is not None else default_count
        if count is None:
            raise ValueError(f"CSV {card.csv_line}行: 人数未確認です。参加人数列または明示的な--default-countを指定してください")
        if not isinstance(count,int) or isinstance(count,bool) or count <= 0:
            raise ValueError("出力人数は正の整数にしてください")
        result.append(count)
    if sum(result) > 1000:
        raise ValueError("首掛けは1回合計1000枚までです。CSVを分けて出力してください")
    return result


def generate(cards: list[Card], output: Path, template="tent", *, font=DEFAULT_FONT,
             event_name="展示イベント",hashtag="つくろがや",default_count=None):
    if template not in ("tent","badges") or not cards:
        raise ValueError("テンプレートと出力対象を確認してください")
    register_font(font)
    fixed = "組み立て表へ裏へ横から見た図前面外側へ立てる見せるマーク内側へ入れる隠すマーク"+"".join(ASSEMBLY_EXAMPLE)+"".join(ASSEMBLY_COPY)+QR_CAPTION
    for card in cards:
        check_glyphs(card.name+card.place+(card.title+card.description+fixed if template == "tent" else ""))
        if template == "tent" and not card.title.strip():
            raise ValueError("卓上カードには作品名を入力してください")
    counts = badge_counts(cards,default_count) if template == "badges" else None
    output.parent.mkdir(parents=True,exist_ok=True)
    c = canvas.Canvas(str(output),pagesize=A4,invariant=1,pageCompression=1)
    c.setTitle(event_name+(" 卓上カード" if template == "tent" else " 首掛け名札"))
    c.setAuthor("ivent_name_card")
    c.setCreator("ivent_name_card")
    d = Drawing(c)
    if template == "tent":
        for card in cards:
            tent_front(d,card,hashtag)
            permission_band(d)
            assembly(d)
            c.showPage()
    else:
        index = 0
        for card,count in zip(cards,counts):
            for _ in range(count):
                if index%8 == 0:
                    if index:
                        c.showPage()
                    for col in range(3):
                        d.line(6+col*99,6,6+col*99,291,dashed=True,weight=.35)
                    for row in range(5):
                        d.line(6,6+row*71.25,204,6+row*71.25,dashed=True,weight=.35)
                x,top = 6+(index%2)*99,6+((index%8)//2)*71.25
                short = len(re.sub(r"\s","",card.name)) <= 12 and "\n" not in card.name
                d.box(card.name,x+6,top+7,87,33,30,14,centered=True,max_lines=1 if short else math.inf)
                place = card.place.replace("・","·").replace("／"," / ")
                latin = all(32 <= ord(ch) <= 126 or ch == "·" for ch in place)
                d.box(place if latin else card.place,x+6,top+49,87,16,18,9,font="Helvetica" if latin else JP,centered=True)
                index += 1
        c.showPage()
    c.save()


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="CSVから4領域の卓上カード、またはA4八面の首掛け名札を作成します。通信・投稿・認証は行いません。")
    parser.add_argument("--template",choices=("tent","badges"),default="tent")
    parser.add_argument("--csv",required=True,type=Path,help="UTF-8 CSV（name,作品,作品説明,x）")
    parser.add_argument("--output",required=True,type=Path,help="出力PDF。印刷はA4縦・片面・100%%")
    parser.add_argument("--font",type=Path,default=DEFAULT_FONT,help="日本語TrueTypeフォント")
    parser.add_argument("--event-name",default="展示イベント",help="PDF文書名のイベント名")
    parser.add_argument("--hashtag",default="つくろがや",help="X投稿用のハッシュタグ（1語）")
    parser.add_argument("--default-count",type=int,help="人数未入力の行にだけ使う明示的な枚数。既知の人数は保持")
    args = parser.parse_args(argv)
    try:
        if args.default_count is not None and args.default_count <= 0:
            raise ValueError("--default-countは正の整数にしてください")
        cards = read_cards(args.csv,allow_blank_work=args.template == "badges")
        generate(cards,args.output,args.template,font=args.font,event_name=args.event_name,hashtag=args.hashtag,default_count=args.default_count)
    except (ValueError,OSError,Image.DecompressionBombError) as error:
        parser.exit(2,f"エラー: {error}\n")
    print(f"PDFを生成しました: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
