import csv
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import re
import sys
import io

# 標準出力のエンコーディングをUTF-8に設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# フォント設定
font_path = "C:\\Windows\\Fonts\\KikaiChokokuJIS-Md.otf"  # 適切なフォントパスに置き換えてください
font_size = 200
font = ImageFont.truetype(font_path, font_size)
small_font = ImageFont.truetype(font_path, font_size - 10)
info_font = ImageFont.truetype(font_path, 80)  # 説明文用の小さいフォント

# テンプレート画像
template_path = "name_plate_sample.png"

# CSVファイルからデータを読み込む
def read_csv(file_path):
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        return [row for row in reader]

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
    # テンプレート画像を開く
    img = Image.open(template_path)
    draw = ImageDraw.Draw(img)
    
    # ファイル名用にサニタイズ
    safe_name = sanitize_filename(data['name'])
    safe_work = sanitize_filename(data['作品'])
    
    # 作品名と出展者名を描画
    work_text = f"作品名：{data['作品']}"
    name_text = f"出展者名：{data['name']}"
    
    # テキスト位置（適宜調整が必要）
    draw.text((100, 100), work_text, font=font, fill="black")
    draw.text((100, 300), name_text, font=font, fill="black")
    
    # QRコード用テキストを生成
    qr_text = f"http://twitter.com/intent/tweet?text={data['作品']}({data['name']})%20%20%23つくろがや&url={data['x']}"
    qr_filename = os.path.join(output_dir, f"{safe_name}_qr.png")
    qr_size = generate_qr_code(qr_text, qr_filename)  # サイズ情報を取得
    
    # QRコードを画像に貼り付け (1.5倍サイズで貼り付け)
    qr_img = Image.open(qr_filename)
    img.paste(qr_img.resize((int(qr_size[0]*1.2), int(qr_size[1]*1.2))), (1900, 1000))  # 位置を調整
    
    # 説明テキスト
    info_text = f"""読み込むと下記の文言が
自動入力されます
「{data['作品']}({data['name']})
#つくろがや
{data['x']}」
コメント等追記いただき
ぜひご活用ください
メンションではないので
通知は行きません"""
    
    # 複数行テキストを描画
    y_position = 1000
    for line in info_text.split('\n'):
        draw.text((150, y_position), line, font=info_font, fill="black")
        y_position += 80  # 行間も少し詰める
    
    # 画像を保存
    output_path = os.path.join(output_dir, f"{safe_name}_plate.png")
    img.save(output_path)
    print(f"生成完了: {output_path}")

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
    for data in data_list:
        try:
            generate_image(data, output_dir)
        except Exception as e:
            print(f"画像生成エラー ({data.get('name', '不明')}): {e}")
    
    print("全ての画像生成が完了しました")

if __name__ == "__main__":
    main()
