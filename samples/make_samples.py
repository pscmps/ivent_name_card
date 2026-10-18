"""Create only fictional CSV and original robot illustrations; no input data needed."""
import csv
from pathlib import Path
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from event_cards import Card, generate, read_cards


def robot(path, portrait=False):
    image=Image.new("RGB",(850,1280) if portrait else (1280,850),(246,239,226))
    d=ImageDraw.Draw(image);w,h=image.size
    d.ellipse((w*.15,h*.8,w*.85,h*.9),fill=(193,166,124))
    d.rectangle((w*.3,h*.18,w*.7,h*.68),fill=(197,157,97),outline=(110,86,53),width=5)
    d.rectangle((w*.42,h*.68,w*.58,h*.83),fill=(175,129,77))
    for x in [.4,.6]:
        d.ellipse((w*(x-.035),h*.32,w*(x+.035),h*.4),fill=(34,63,70))
    d.ellipse((w*.47,h*.48,w*.53,h*.57),fill=(175,91,59))
    image.save(path)


def main():
    folder=ROOT/"samples";images=folder/"images";images.mkdir(parents=True,exist_ok=True)
    robot(images/"robot-landscape.png");robot(images/"robot-portrait.png",True)
    rows=[
        ["架空工作室 ほしの","星あかりの小さなロボット","段ボールと木の部品でつくった架空のロボットです。動く仕組みや材料について気軽に話しかけてください。","https://x.com/example_maker","10/24,25  A-1a","images/robot-landscape.png","3"],
        ["架空工作室 そら","木と光のからくり","写真なしでも説明を大きく載せられる架空の作品です。","","10/24  B-2 / 10/25  C-3","","2"],
        ["日本語の長い出展者名を検証する架空工作研究室と仲間たち"[:30],("長い日本語の作品名と折り返しを確認するための架空展示作品です。"*5)[:100],("これは百文字の架空の作品説明です。作品の仕組みと素材、見どころを紹介します。"*5)[:100],"@example_maker","","images/robot-portrait.png","4"],
    ]
    path=folder/"fictional.csv"
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream);writer.writerow(["name","作品","作品説明","x","場所","画像","参加人数"]);writer.writerows(rows)
    cards=read_cards(path)
    generate(cards,folder/"tent-cards.pdf",event_name="架空の展示イベント")
    generate(cards,folder/"neck-badges.pdf","badges",event_name="架空の展示イベント")
    print("Created three fictional exhibitors, three tent pages and nine neck badges.")


if __name__=="__main__":main()
