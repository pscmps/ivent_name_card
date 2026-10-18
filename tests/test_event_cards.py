import contextlib
import csv
import itertools
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from event_cards import ASSEMBLY_COPY,Card,badge_counts,generate,photo,positive_count,read_cards,tweet_intent,x_profile
from urllib.parse import parse_qs,urlparse


@contextlib.contextmanager
def workspace_fixture():
    parent=(ROOT/".local").resolve();parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cards-test-",dir=parent) as raw:
        folder=Path(raw).resolve();folder.relative_to(parent)
        yield folder


def fixture_csv(folder,rows,optional=()):
    path=folder/"fictional.csv"
    with path.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.writer(stream);writer.writerow(["name","作品","作品説明","x",*optional]);writer.writerows(rows)
    return path


class EventCardsTests(unittest.TestCase):
    def test_csv_keeps_original_columns_and_optional_count_place_image(self):
        with workspace_fixture() as folder:
            path=fixture_csv(folder,[[" 架空名 ","架空作品","架空説明","@example_maker","A-1a","10/24,25","3","robot.png"]],("場所","日付","participantCount","画像"))
            card=read_cards(path)[0]
            self.assertEqual(card.name,"架空名");self.assertEqual(card.participant_count,3)
            self.assertEqual(card.place,"10/24,25  A-1a");self.assertEqual(card.image,folder/"robot.png")
            self.assertEqual(card.x_profile,"https://x.com/example_maker")
            with self.assertRaises(ValueError):read_cards(fixture_csv(folder,[["","作品","説明",""]]))

    def test_intent_encodes_author_work_hashtag_and_only_optional_x_profile(self):
        for account in ["@example_maker","https://x.com/example_maker?s=21","https://twitter.com/example_maker"]:
            value=tweet_intent("作品 & # 日本語","架空の作者",x_profile(account))
            url=urlparse(value);query=parse_qs(url.query)
            self.assertEqual(url.scheme,"https");self.assertEqual(url.netloc,"twitter.com");self.assertEqual(url.path,"/intent/tweet")
            self.assertEqual(query,{"text":["作品 & # 日本語(架空の作者)  #つくろがや"],"url":["https://x.com/example_maker"]})
        for value in ["","https://x.com/","https://x.com/?s=21"]:
            query=parse_qs(urlparse(tweet_intent("作品","架空名",x_profile(value))).query)
            self.assertEqual(set(query),{"text"})
        with self.assertRaises(ValueError):x_profile("https://example.invalid/other")

    def test_missing_count_stays_unknown_until_explicit_fallback(self):
        cards=[Card("架空名","作品","",None,participant_count=3),Card("架空名二","作品","",None)]
        with self.assertRaisesRegex(ValueError,"人数未確認"):badge_counts(cards,None)
        self.assertEqual(badge_counts(cards,2),[3,2]);self.assertIsNone(cards[1].participant_count)
        for value in ["0","-1","1.5","true","9007199254740992"]:
            with self.assertRaises(ValueError):positive_count(value)
        with self.assertRaisesRegex(ValueError,"1000"):badge_counts([Card("架空名","作品","",None,participant_count=1001)],None)

    def test_equilateral_mountains_and_minimal_cuts_for_all_eight_selections(self):
        side=92;self.assertEqual(21+side*3,297)
        v=lambda a:(math.cos(a),math.sin(a))
        points=[(0.,0.)]
        for angle in [0,2*math.pi/3,4*math.pi/3]:
            t=v(angle);points.append((points[-1][0]+side*t[0],points[-1][1]+side*t[1]))
        self.assertAlmostEqual(points[-1][0],0);self.assertAlmostEqual(points[-1][1],0)
        for a,b in zip(points,points[1:]):self.assertAlmostEqual(math.dist(a,b),92)
        # n=(-sin(theta),-cos(theta)) in the paper's printed-side convention.
        for before in [-2*math.pi/3,0,2*math.pi/3]:
            after=before+2*math.pi/3
            tangent=(math.cos(after),math.sin(after));normal=(math.sin(before),-math.cos(before))
            self.assertLess(sum(a*b for a,b in zip(tangent,normal)),0)
        for choice in itertools.product([0,1],repeat=3):
            outside={g+3*c for g,c in enumerate(choice)}
            cuts=[i*35 for i in range(1,6) if ((i-1 in outside)!=(i in outside))]
            if len(set(choice))==1:self.assertEqual(cuts,[105])
            for i in range(1,6):
                if i*35 not in cuts:self.assertEqual(i-1 in outside,i in outside)

    def test_vector_tent_text_and_unsupported_glyphs_without_network(self):
        with workspace_fixture() as folder:
            path=folder/"tent.pdf"
            with patch.object(socket,"create_connection",side_effect=AssertionError("No network")):
                generate([Card("架空名","作品 & 日本語","説明",None,"10/24 A-1a")],path)
            pdf=PdfReader(path);self.assertEqual(len(pdf.pages),1)
            text="".join(pdf.pages[0].extract_text().split())
            for copy in ASSEMBLY_COPY:self.assertIn("".join(copy.split()),text)
            self.assertNotIn("根元まで21mm",text)
            with self.assertRaisesRegex(ValueError,"フォントにない文字"):
                generate([Card("架空🤖","作品","",None)],folder/"bad.pdf")
            self.assertFalse((folder/"bad.pdf").exists())

    def test_photo_orientation_metadata_and_type(self):
        with workspace_fixture() as folder:
            path=folder/"orientation.jpg";image=Image.new("RGB",(80,40),"red")
            exif=Image.Exif();exif[274]=6;exif[270]="FICTIONAL-METADATA";image.save(path,exif=exif)
            clean=photo(path);self.assertEqual(clean.size,(40,80));self.assertEqual(clean.info,{})
            image.save(folder/"unsupported.gif")
            with self.assertRaises(ValueError):photo(folder/"unsupported.gif")

    def test_legacy_no_argument_command_with_fictional_csv_is_preserved(self):
        with workspace_fixture() as folder:
            path=fixture_csv(folder,[["Fictional A","架空作品一","説明",""],["Fictional B","架空作品二","説明","https://x.com/"],["Fictional C","架空作品三","説明","@example_maker"]])
            path.replace(folder/"name_list.csv")
            Image.new("RGB",(3200,2200),"white").save(folder/"name_plate_sample.png")
            result=subprocess.run([sys.executable,str(ROOT/"generate_name_plates.py")],cwd=folder,capture_output=True,text=True,encoding="utf-8",timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn("エラー",result.stdout)
            self.assertEqual(len(PdfReader(folder/"output"/"all_name_plates.pdf").pages),2)
            self.assertEqual(len(list((folder/"output").glob("*_plate.png"))),3)

    def test_modern_cli_dispatch_preserves_four_columns_and_rejects_unknown_badge_count(self):
        with workspace_fixture() as folder:
            path=fixture_csv(folder,[["架空名","","",""]])
            command=[sys.executable,str(ROOT/"generate_name_plates.py"),"--template","badges","--csv",str(path),"--output",str(folder/"badges.pdf")]
            result=subprocess.run(command,cwd=folder,capture_output=True,text=True,encoding="utf-8",timeout=30)
            self.assertEqual(result.returncode,2);self.assertIn("人数未確認",result.stderr)
            result=subprocess.run(command+["--default-count","2"],cwd=folder,capture_output=True,text=True,encoding="utf-8",timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            pdf=PdfReader(folder/"badges.pdf");self.assertEqual(len(pdf.pages),1)
            self.assertEqual("".join(pdf.pages[0].extract_text().split()).count("架空名"),2)


if __name__=="__main__":unittest.main()
