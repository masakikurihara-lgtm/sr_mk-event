import re
from datetime import datetime
import io
from bs4 import BeautifulSoup
import pandas as pd
import pytz

# 日本時間(JST)の設定
JST = pytz.timezone("Asia/Tokyo")


def parse_html_to_dataframe(html_file_path):
    # ① HTMLファイルを満たして解析準備
    with open(html_file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    parsed_data = []

    # ② イベント1件ごとにループ処理 (liタグのlist-innerクラスを含む単位を基準にします)
    # 構造的に、各イベントの枠組みを探索
    event_nodes = soup.find_all("div", class_="list-inner")

    for node in event_nodes:
        # 親要素の <li> を取得することで、後半の「list-sub-box」エリアも一緒に探せるようにします
        li_parent = node.find_parent("li")
        if not li_parent:
            continue

        try:
            # --- 1. 画像URL ---
            img_tag = li_parent.find("img", class_="img-main")
            image_url = img_tag["src"] if img_tag else ""

            # --- 2. イベント名 ---
            # tx-title クラスのテキストを取得
            title_tag = li_parent.find("p", class_="tx-title")
            event_name = title_tag.get_text(strip=True) if title_tag else ""

            # --- 3. イベントID ---
            # aタグの href から "event_id=XXXX" の数字を抽出
            event_id = ""
            edit_link = li_parent.find("a", href=re.compile(r"event_id=\d+"))
            if edit_link:
                match = re.search(r"event_id=(\d+)", edit_link["href"])
                if match:
                    event_id = match.group(1)

            # --- 4. イベント開始日・終了日 (タイムスタンプ形式) ---
            started_at_ts = ""
            ended_at_ts = ""

            # 「このイベントは終了しています」が含まれるpタグを探す
            p_tags = li_parent.find_all("p", style=re.compile(r"color:\s*gray"))
            for p in p_tags:
                text = p.get_text(strip=True)
                if "このイベントは終了しています" in text:
                    # 改行や文字列を無視して「YYYY/MM/DD HH:MM - YYYY/MM/DD HH:MM」のパターンを抽出
                    date_match = re.search(
                        r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})\s*-\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})",
                        text,
                    )
                    if date_match:
                        start_str = date_match.group(1)  # 例: "2022/07/25 18:00"
                        end_str = date_match.group(2)  # 例: "2022/08/03 21:59"

                        # datetimeオブジェクトに変換後、タイムスタンプに変換
                        dt_start = datetime.strptime(
                            start_str, "%Y/%m/%d %H:%M"
                        )
                        dt_end = datetime.strptime(end_str, "%Y/%m/%d %H:%M")

                        # タイムゾーンをJSTとして認識させてUnixTimeに
                        started_at_ts = int(
                            JST.localize(dt_start).timestamp()
                        )
                        ended_at_ts = int(JST.localize(dt_end).timestamp())
                    break

            # 5つの情報が揃っていれば（または最低限IDと名前があれば）リストに追加
            if event_id or event_name:
                parsed_data.append(
                    {
                        "event_id": event_id,
                        "event_name": event_name,
                        "image_m": image_url,  # 既存ツールに合わせてimage_mに
                        "started_at": started_at_ts,
                        "ended_at": ended_at_ts,
                    }
                )

        except Exception as e:
            # 特定の行でエラーが起きても次へ進める
            continue

    # ③ 結果をデータフレーム化
    df = pd.DataFrame(parsed_data)
    return df


# --- 実行部分 ---
if __name__ == "__main__":
    # 9ページ分のHTMLをまとめたファイルのパスを指定
    html_file = "all_events.html"

    try:
        result_df = parse_html_to_dataframe(html_file)

        # 重複があれば除外
        result_df.drop_duplicates(subset=["event_id"], inplace=True)

        print(f"🎉 抽出完了！ 合計: {len(result_df)} 件のイベントが見つかりました。")

        # 手動補完がしやすいようにCSVファイルとして保存
        result_df.to_csv("extracted_past_events.csv", index=False, encoding="utf-8-sig")
        print("💾 'extracted_past_events.csv' として保存しました。")

    except FileNotFoundError:
        print(
            f"❌ エラー: {html_file} が見つかりません。HTMLソースをこの名前で保存してください。"
        )