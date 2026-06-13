import re
from datetime import datetime
import io
from bs4 import BeautifulSoup
import pandas as pd
import pytz
import streamlit as st

# 日本時間(JST)の設定
JST = pytz.timezone("Asia/Tokyo")

# レイアウトをワイドモードに設定
st.set_page_config(layout="wide")


def parse_html_to_dataframe(html_content, exclude_ids_set):
    """HTMLを解析し、かつ指定された重複IDを除外したデータフレームを返す関数"""
    soup = BeautifulSoup(html_content, "html.parser")
    parsed_data = []

    # イベント1件ごとにループ処理 (liタグのlist-innerクラスを含む単位を基準にします)
    event_nodes = soup.find_all("div", class_="list-inner")

    for node in event_nodes:
        li_parent = node.find_parent("li")
        if not li_parent:
            continue

        try:
            # --- 1. イベントID ---
            event_id = ""
            edit_link = li_parent.find("a", href=re.compile(r"event_id=\d+"))
            if edit_link:
                match = re.search(r"event_id=(\d+)", edit_link["href"])
                if match:
                    event_id = match.group(1)

            # 🚨 【ここがポイント】既存のIDセットに含まれていたら、このイベントの処理はスキップ（追加しない）
            if event_id in exclude_ids_set:
                continue

            # --- 2. イベント名 ---
            title_tag = li_parent.find("p", class_="tx-title")
            event_name = title_tag.get_text(strip=True) if title_tag else ""

            # --- 3. 画像URL ---
            img_tag = li_parent.find("img", class_="img-main")
            image_url = img_tag["src"] if img_tag else ""

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

            # --- 5. イベントURLキー ---
            event_url_key = ""
            public_link = li_parent.find("a", href=re.compile(r"^/event/[^?]+"))
            if public_link:
                url_match = re.search(r"^/event/([^?#/]+)", public_link["href"])
                if url_match:
                    event_url_key = url_match.group(1)

            # 必須項目が揃っていればリストに追加
            if event_id or event_name:
                parsed_data.append(
                    {
                        "event_id": event_id,
                        "event_name": event_name,
                        "event_url_key": event_url_key,
                        "image_m": image_url,
                        "started_at": started_at_ts,
                        "ended_at": ended_at_ts,
                    }
                )

        except Exception:
            continue

    df = pd.DataFrame(parsed_data)
    return df


# ――― 🖥️ Streamlit 画面表示エリア ―――
st.title("📂 過去イベントデータ抽出ツール（重複除外版）")
st.write(
    "既存CSVのイベントIDを指定することで、重複データを予め完全に落とした「新規の過去イベントだけ」をCSVで書き出します。"
)

st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("🚫 1. 重複させたくないイベントID")
    # 既存CSVのID列をそのままコピペしてもらうエリア（カンマ、スペース、改行、どれでも自動分離します）
    id_input = st.text_area(
        "既存CSVの『event_id』列の数字をここに丸ごと貼り付けてください（改行のままでOK）",
        height=400,
        placeholder="28941\n28942\n28943",
    )

with col2:
    st.subheader("📝 2. 過去イベントのHTMLを貼り付け")
    html_input = st.text_area(
        "9ページ分のHTMLソースをここにペーストしてください",
        height=400,
        placeholder="<li><div class=\"list-inner\">...",
    )

st.markdown("---")

# 解析ボタン
if st.button("🚀 3. 重複を排除してデータを抽出する", type="primary"):
    if html_input.strip():
        with st.spinner("HTMLを解析中（重複チェック実施中）..."):
            # 入力された既存IDの文字列をセット型（検索を高速にするため）に整形
            # 数字だけを正規表現で切り出してリスト化
            exclude_ids = re.findall(r"\d+", id_input)
            exclude_ids_set = set(exclude_ids)

            # 入力されたHTMLと、除外したいIDのリストを渡して解析
            result_df = parse_html_to_dataframe(html_input, exclude_ids_set)

            if not result_df.empty:
                # HTML内の重複も念のため除外
                result_df.drop_duplicates(subset=["event_id"], inplace=True)

                st.success(
                    f"🎉 抽出が完了しました！\n"
                    f"・指定された既存IDにより除外された重複: {len(exclude_ids_set)} 件の対象をチェック\n"
                    f"・重複せずに新しく見つかった過去イベント: {len(result_df)} 件"
                )

                # プレビュー表示
                st.subheader("📊 抽出データプレビュー（既存CSVにない新規データのみ）")
                st.dataframe(result_df, use_container_width=True)

                # ダウンロード用ボタンの作成（UTF-8 BOM付きCSV）
                csv_bytes = result_df.to_csv(
                    index=False, encoding="utf-8-sig"
                ).encode("utf-8-sig")

                st.markdown("---")
                st.download_button(
                    label="📥 4. 既存CSVに追加するための新規過去イベントCSVをダウンロード",
                    data=csv_bytes,
                    file_name="new_past_events_only.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.warning(
                    "⚠️ 条件に一致する新しいイベントが見つかりませんでした。すべて重複しているか、HTMLの範囲が正しいか確認してください。"
                )
    else:
        st.error(
            "❌ HTMLソースコードが入力されていません。貼り付けてからボタンを押してください。"
        )