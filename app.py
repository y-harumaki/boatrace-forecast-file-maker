from __future__ import annotations

import shutil
from pathlib import Path

import streamlit as st

from src.builders import build_racelist_detail, build_results_raw, build_racer_course_style_summary
from src.prompt_builder import build_chatgpt_prompt
from src.validators import validate_dates, validate_join_coverage, validate_racelist_detail, validate_results_raw
from src.zip_utils import make_zip

st.set_page_config(page_title="BOATRACE 最終日予想ファイル作成", layout="wide")

st.title("BOATRACE 最終日予想ファイル作成ツール")
st.caption("APIは使わず、ChatGPTブラウザに添付する4ファイルを作成します。")

with st.expander("このツールでやること", expanded=True):
    st.markdown(
        """
- 初日〜前日の **結果ページ** から、選手別・コース別傾向CSVを作成します。
- 最終日は **出走表ページだけ** を取得します。結果・払戻・オッズ・直前情報は取得しません。
- `README.md` と `展開.txt` を同梱したzipを作成します。
- 予想は、このzipをChatGPTブラウザに添付して実行します。
        """
    )

col1, col2 = st.columns([1, 2])
with col1:
    jcd = st.text_input("場コード jcd", value="14", help="例: 桐生=01, 戸田=02, ... 鳴門=14")
with col2:
    st.write(" ")
    st.info("場コードは2桁に自動補正します。例: 7 → 07")

c1, c2, c3 = st.columns(3)
with c1:
    start_date = st.date_input("初日")
with c2:
    prev_date = st.date_input("前日")
with c3:
    final_date = st.date_input("最終日")

save_debug_html = st.checkbox("デバッグ用に取得HTMLも保存する", value=False)
run = st.button("4ファイルを作成", type="primary")

if run:
    jcd = str(jcd).zfill(2)
    start_hd = start_date.strftime("%Y%m%d")
    prev_hd = prev_date.strftime("%Y%m%d")
    final_hd = final_date.strftime("%Y%m%d")

    date_msgs = validate_dates(start_hd, prev_hd, final_hd)
    if any(m.startswith("[NG]") for m in date_msgs):
        for m in date_msgs:
            st.error(m)
        st.stop()
    for m in date_msgs:
        st.write(m)

    output_dir = Path("outputs") / f"jcd{jcd}_{final_hd}"
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "debug_html" if save_debug_html else None

    try:
        with st.status("ファイル作成中...", expanded=True) as status:
            st.write("最終日の出走表を取得しています。")
            racelist_df = build_racelist_detail(jcd, final_hd, debug_dir=debug_dir)
            racelist_path = output_dir / f"racelist_detail_jcd{jcd}_{final_hd}.csv"
            racelist_df.to_csv(racelist_path, index=False, encoding="utf-8-sig")

            st.write("初日〜前日の結果を取得しています。")
            results_raw_df = build_results_raw(jcd, start_hd, prev_hd, debug_dir=debug_dir)
            raw_path = output_dir / f"race_results_raw_jcd{jcd}_{start_hd}_{prev_hd}.csv"
            results_raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")

            st.write("選手別・コース別傾向を集計しています。")
            summary_df = build_racer_course_style_summary(results_raw_df)
            summary_path = output_dir / f"racer_course_style_summary_jcd{jcd}_{start_hd}_{prev_hd}.csv"
            summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

            st.write("固定ファイルとzipを作成しています。")
            readme_path = output_dir / "README.md"
            tenkai_path = output_dir / "展開.txt"
            shutil.copy(Path("fixed_files") / "README.md", readme_path)
            shutil.copy(Path("fixed_files") / "展開.txt", tenkai_path)

            prompt = build_chatgpt_prompt(jcd, start_hd, prev_hd, final_hd)
            prompt_path = output_dir / f"chatgpt_prompt_jcd{jcd}_{final_hd}.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            zip_path = output_dir / f"boatrace_forecast_files_jcd{jcd}_{final_hd}.zip"
            make_zip(zip_path, [racelist_path, summary_path, readme_path, tenkai_path])
            status.update(label="完了", state="complete")
    except Exception as e:
        st.exception(e)
        st.stop()

    st.success("4ファイルを作成しました。")

    st.subheader("作成ファイル")
    st.write(f"- `{racelist_path.name}`")
    st.write(f"- `{summary_path.name}`")
    st.write("- `README.md`")
    st.write("- `展開.txt`")

    with open(zip_path, "rb") as f:
        st.download_button(
            label="4ファイルzipをダウンロード",
            data=f,
            file_name=zip_path.name,
            mime="application/zip",
        )

    st.subheader("チェック結果")
    t1, t2, t3 = st.tabs(["出走表", "結果raw", "結合カバレッジ"])
    with t1:
        for msg in validate_racelist_detail(racelist_df):
            st.write(msg)
        st.dataframe(racelist_df.head(20), use_container_width=True)
    with t2:
        for msg in validate_results_raw(results_raw_df):
            st.write(msg)
        st.dataframe(results_raw_df.head(20), use_container_width=True)
    with t3:
        for msg in validate_join_coverage(racelist_df, summary_df):
            st.write(msg)
        st.dataframe(summary_df.head(20), use_container_width=True)

    st.subheader("ChatGPT貼り付け用プロンプト")
    st.text_area("zip内の4ファイルを添付したうえで、この文章をChatGPTに貼ってください。", prompt, height=420)
