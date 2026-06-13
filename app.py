import re
from datetime import datetime
import io
from bs4 import BeautifulSoup
import pandas as pd
import pytz
import streamlit as st  # ✅ Streamlit用のインポートを追加

# 日本時間(JST)の設定
JST = pytz.timezone("Asia/Tokyo")

# レイアウトをワイドモードに設定
st.set_page_config(layout="wide")

def parse_html_to_dataframe(html_content):
    """HTMLテキスト（文字列）を解析してデータフレームを返す関数"""
    soup = BeautifulSoup(html_content, "html.parser")
    parsed_data = []

    # イベント1件ごとにループ処理 (liタグのlist-innerクラスを含む単位を基準にします)
    event_nodes = soup.find_all("div", class_="list-inner")

    for node in event_nodes:
        li_parent = node.find_parent("li")
        if not li_parent:
            continue

        try:
            # --- 1. 画像URL ---
            img_tag = li_parent.find("img", class_="img-main")
            image_url = img_tag["src"] if img_tag else ""

            # --- 2. イベント名 ---
            title_tag = li_parent.find("p", class_="tx-title")
            event_name = title_tag.get_text(strip=True) if title_tag else ""

            # --- 3. イベントID ---
            event_id = ""
            edit_link = li_parent.find("a", href=re.compile(r"event_id=\d+"))
            if edit_link:
                match = re.search(r"event_id=(\d+)", edit_link["href"])
                if match:
                    event_id = match.group(1)

            # --- 4. イベント開始日・終了日 (タイムスタンプ形式) ---
            started_at_ts = ""
            ended_at_ts = ""

            p_tags = li_parent.find_all("p", style=re.compile(r"color:\s*gray"))
            for p in p_tags:
                text = p.get_text(strip=True)
                if "このイベントは終了しています" in text:
                    date_match = re.search(
                        r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})\s*-\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})",
                        text,
                    )
                    if date_match:
                        start_str = date_match.group(1)
                        end_str = date_match.group(2)

                        dt_start = datetime.strptime(start_str, "%Y/%m/%d %H:%M")
                        dt_end = datetime.strptime(end_str, "%Y/%m/%d %H:%M")

                        started_at_ts = int(JST.localize(dt_start).timestamp())
                        ended_at_ts = int(JST.localize(dt_end).timestamp())
                    break

            # --- 5. 【追加】イベントURLキー (公開済みイベントページの識別子) ---
            event_url_key = ""
            public_link = li_parent.find("a", href=re.compile(r"^/event/[^?]+"))
            if public_link:
                # "/event/xxxx" の部分から "xxxx" を正規表現で取り出す
                url_match = re.search(r"^/event/([^?#/]+)", public_link["href"])
                if url_match:
                    event_url_key = url_match.group(1)

            # 必須項目が揃っていればリストに追加
            if event_id or event_name:
                parsed_data.append(
                    {
                        "event_id": event_id,
                        "event_name": event_name,
                        "event_url_key": event_url_key,  # 🚀 追加された項目
                        "image_m": image_url,
                        "started_at": started_at_ts,
                        "ended_at": ended_at_ts,
                    }
                )

        except Exception as e:
            continue

    df = pd.DataFrame(parsed_data)
    return df


# ――― 🖥️ Streamlit 画面表示エリア ―――
st.title("📂 過去イベントHTMLデータ一括抽出ツール")
st.write("管理画面（オーガナイザーページ）のHTMLソースから、過去イベントの必要情報を一括でCSVに変換します。")

st.markdown("---")

# 巨大なHTMLをそのままコピペして入力できるテキストボックスを配置
html_input = st.text_area(
    "1. ここに9ページ分のHTMLソースを丸ごと貼り付けてください（続きのまま一括で貼り付けてOKです）",
    height=400,
    placeholder="<li><div class=\"list-inner\">... のようなHTMLソースをここにペーストしてください"
)

# 解析ボタン
if st.button("2. HTMLを解析してデータを抽出する", type="primary"):
    if html_input.strip():
        with st.spinner("HTMLを解析中..."):
            # 入力されたHTMLをそのまま関数に渡して解析
            result_df = parse_html_to_dataframe(html_input)

            if not result_df.empty:
                # 重複があれば除外
                result_df.drop_duplicates(subset=["event_id"], inplace=True)
                
                st.success(f"🎉 解析が完了しました！ 合計 {len(result_df)} 件のイベントを抽出しました。")
                
                # プレビュー表示
                st.subheader("📊 抽出データプレビュー")
                st.dataframe(result_df, use_container_width=True)

                # ダウンロード用ボタンの作成（UTF-8 BOM付きCSV）
                csv_bytes = result_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.markdown("---")
                st.download_button(
                    label="📥 3. 抽出した過去イベントCSVをダウンロード",
                    data=csv_bytes,
                    file_name="extracted_past_events.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ 指定されたHTML構造（イベント情報）が見つかりませんでした。貼り付けたソースを確認してください。")
    else:
        st.error("❌ HTMLソースコードが入力されていません。貼り付けてからボタンを押してください。")