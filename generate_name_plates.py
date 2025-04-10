import csv
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import re
import sys
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import math

# 標準出力のエンコーディングをUTF-8に設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# フォント設定
try:
    # 正しいパス形式で試す
    font_path = "C:/Users/xx/AppData/Local/Microsoft/Windows/Fonts/BestTen-DOT.otf"
    ImageFont.truetype(font_path, 10)  # テスト読み込み
except:
    # 失敗したらWindows標準フォントを使用
    font_path = "C:/Windows/Fonts/meiryo.ttc"

font_size = 200
font = ImageFont.truetype(font_path, font_size)
small_font = ImageFont.truetype(font_path, font_size - 10)
info_font = ImageFont.truetype(font_path, 100)  # 説明文用の小さいフォント

# テンプレート画像
template_path = "name_plate_sample.png"

# CSVファイルからデータを読み込む
def read_csv(file_path):
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        # 各フィールドの前後空白とタブを削除
        return [
            {k: v.strip(' \t') for k, v in row.items()} 
            for row in reader
        ]

# 特殊文字をアンダースコアに置換
def sanitize_filename(filename):
    # 特殊文字と非ASCII文字をアンダースコアに置換
    return re.sub(r'[\\/:*?"<>|\t\n\r\x00-\x1f\x7f-\xff]', '_', filename)

# QRコードを生成する
def generate_qr_code(text, filename):
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=12,  # 10から15に変更 (1.5倍)
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(filename)
        return img.size  # サイズ情報を返す
    except Exception as e:
        print(f"QRコード生成エラー: {e}")
        raise

# 画像を生成する
def generate_image(data, output_dir):
    # 出力ディレクトリ作成
    qr_output_dir = os.path.join(output_dir, "qr_codes")
    os.makedirs(qr_output_dir, exist_ok=True)
    
    # テンプレート画像を開く
    img = Image.open(template_path)
    draw = ImageDraw.Draw(img)
    
    # ファイル名用にサニタイズ
    safe_name = sanitize_filename(data['name'])
    safe_work = sanitize_filename(data['作品'])
    
    # 作品名と出展者名を描画
    work_text = f"作品名：{data['作品']}"
    name_text = f"出展者名：{data['name']}"
    
    # 文字数制限
    max_length = 8
    
    # フォント選択
    work_font = info_font if len(data['作品']) > max_length else font
    name_font = info_font if len(data['name']) > max_length else font
    
    # テキスト位置
    work_y = 100
    name_y = 300
    
    # 作品名を描画
    draw.text((100, work_y), work_text, font=work_font, fill="black")
    
    # 出展者名を描画
    draw.text((100, name_y), name_text, font=name_font, fill="black")
    
    # QRコード用テキストを生成
    # Xアカウントの有無をチェック
    has_x_account = data['x'] != "https://x.com/" and data['x'] != "https://x.com"
    
    # QRコードのテキスト生成
    if has_x_account:
        qr_text = f"http://twitter.com/intent/tweet?text={data['作品']}({data['name']})%20%20%23つくろがや&url={data['x']}"
    else:
        qr_text = f"http://twitter.com/intent/tweet?text={data['作品']}({data['name']})%20%20%23つくろがや"
    
    qr_filename = os.path.join(qr_output_dir, f"{safe_name}_qr.png")
    qr_size = generate_qr_code(qr_text, qr_filename)
    
    # QRコードを画像に貼り付け (1.5倍サイズで貼り付け)
    qr_img = Image.open(qr_filename)
    img.paste(qr_img.resize((int(qr_size[0]*1.2), int(qr_size[1]*1.2))), (1900, 1000))  # 位置を調整
    
    # 説明テキスト - Xアカウントの有無に応じて変更
    if has_x_account:
        info_text = f"""右→のQRコードを
読み込むと下記の文言が
自動入力されます
「{data['作品']}
({data['name']})
#つくろがや
{data['x']}」
コメント等追記いただき
ぜひご活用ください

※メンションではないので
通知は行きません"""
    else:
        info_text = f"""右→のQRコードを
読み込むと下記の文言が
自動入力されます
「{data['作品']}
({data['name']})
#つくろがや」
コメント等追記いただき
ぜひご活用ください

※メンションではないので
通知は行きません"""
    
    # 複数行テキストを描画
    y_position = 600
    for line in info_text.split('\n'):
        draw.text((150, y_position), line, font=info_font, fill="black")
        y_position += 100  # 行間も少し詰める
    
    # 画像を保存
    output_path = os.path.join(output_dir, f"{safe_name}_plate.png")
    img.save(output_path)
    return output_path  # 生成したファイルのパスを返す

# A4サイズのPDFに画像を2枚ずつ配置する関数
def create_pdf_with_images(image_paths, output_pdf_path):
    # A4サイズの定義
    a4_width, a4_height = A4  # (595.28, 841.89) ポイント
    
    # A5サイズの定義（A4の半分）- 上下に配置するため高さを半分に
    a5_width = a4_width
    a5_height = a4_height / 2
    
    # PDFキャンバスを作成
    c = canvas.Canvas(output_pdf_path, pagesize=A4)
    
    # 画像を2枚ずつ配置
    total_pages = math.ceil(len(image_paths) / 2)
    
    for i in range(0, len(image_paths), 2):
        # 上側の画像
        if i < len(image_paths):
            img = Image.open(image_paths[i])
            # 画像をA5サイズに合わせてリサイズ
            img = img.resize((int(a5_width), int(a5_height)), Image.LANCZOS)
            temp_path = f"temp_top_{i}.png"
            img.save(temp_path)
            c.drawImage(temp_path, 0, a5_height, width=a5_width, height=a5_height)
            os.remove(temp_path)
        
        # 下側の画像
        if i + 1 < len(image_paths):
            img = Image.open(image_paths[i + 1])
            # 画像をA5サイズに合わせてリサイズ
            img = img.resize((int(a5_width), int(a5_height)), Image.LANCZOS)
            temp_path = f"temp_bottom_{i}.png"
            img.save(temp_path)
            c.drawImage(temp_path, 0, 0, width=a5_width, height=a5_height)
            os.remove(temp_path)
        
        # ページを終了し、次のページへ
        c.showPage()
    
    # PDFを保存
    c.save()
    return output_pdf_path

# メイン処理
def main():
    # 出力ディレクトリ作成
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    # CSVからデータ読み込み
    try:
        data_list = read_csv("name_list.csv")
    except Exception as e:
        print(f"CSV読み込みエラー: {e}")
        return
    
    # 各データに対して画像生成
    generated_files = []  # 生成されたファイルのリスト
    for data in data_list:
        try:
            output_path = generate_image(data, output_dir)
            generated_files.append(output_path)
            print(f"生成完了: {output_path}")
        except Exception as e:
            print(f"画像生成エラー ({data.get('name', '不明')}): {e}")
    
    # PDFに出力
    try:
        pdf_path = os.path.join(output_dir, "all_name_plates.pdf")
        create_pdf_with_images(generated_files, pdf_path)
        print(f"PDFを生成しました: {pdf_path}")
    except Exception as e:
        print(f"PDF生成エラー: {e}")
    
    print("全ての画像生成が完了しました")

if __name__ == "__main__":
    main()
