from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import streamlit as st

from src.builders import (
    build_racelist_detail,
    build_results_raw,
    build_racer_course_style_summary,
    add_reliability_flags,
)
from src.validators import (
    validate_racelist_detail,
    validate_results_raw,
)
from src.prompt_builder import build_chatgpt_prompt
from src.zip_utils import make_zip


st.set_page_config(
    page_title="BOATRACE 最終日予想ファイル作成",
    layout="wide",
)

st.title("BOATRACE 最終日予想ファイル作成ツール")

st.write(
    "場コードと期間を入力すると、ChatGPTに添付する4ファイルを作成します。"
)

st.warning(
    "最終日は出走表 racelist のみ取得します。結果・払戻・オッズ・直前情報は取得しません。"
)

jcd = st.text_input("場コード jcd", value="09")

col1, col2, col3 = st.columns(3)

with col1:
    start_date = st.date_input("初日")

with col2:
    prev_date = st.date_input("前日")

with col3:
    final_date = st.date_input("最終日")

debug_mode = st.checkbox(
    "デバッグCSVもzipに入れる",
    value=True,
)

run = st.button("4ファイルを作成")

if run:
    jcd = str(jcd).zfill(2)
    start_hd = start_date.strftime("%Y%m%d")
    prev_hd = prev_date.strftime("%Y%m%d")
    final_hd = final_date.strftime("%Y%m%d")

    if not (start_hd <= prev_hd < final_hd):
        st.error("日付条件が不正です。初日 <= 前日 < 最終日 になるようにしてください。")
        st.stop()

    output_dir = Path("outputs") / f"jcd{jcd}_{final_hd}"
    output_dir.mkdir(parents=True, exist_ok=True)

    st.info("最終日の出走表を取得しています...")
    racelist_df = build_racelist_detail(jcd, final_hd)

    racelist_path = output_dir / f"racelist_detail_jcd{jcd}_{final_hd}.csv"
    racelist_df.to_csv(racelist_path, index=False, encoding="utf-8-sig")

    st.info("初日〜前日の結果を取得しています...")
    results_raw_df = build_results_raw(jcd, start_hd, prev_hd)

    raw_path = output_dir / f"race_results_raw_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    results_raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")

    st.info("選手別・コース別傾向を集計しています...")
    summary_df = build_racer_course_style_summary(results_raw_df)
    summary_df = add_reliability_flags(summary_df)

    summary_path = output_dir / f"racer_course_style_summary_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    readme_src = Path("fixed_files") / "README.md"

    tenkai_src_candidates = [
        Path("fixed_files") / "展開.txt",
        Path("fixed_files") / "tenkai.txt",
    ]

    tenkai_src = None
    for p in tenkai_src_candidates:
        if p.exists():
            tenkai_src = p
            break

    if tenkai_src is None:
        st.error("fixed_files/展開.txt または fixed_files/tenkai.txt が見つかりません。")
        st.stop()

    readme_path = output_dir / "README.md"
    tenkai_path = output_dir / "展開.txt"

    shutil.copy(readme_src, readme_path)
    shutil.copy(tenkai_src, tenkai_path)

    debug_files = []

    racelist_errors_df = racelist_df.attrs.get("errors_df", pd.DataFrame())
    results_errors_df = results_raw_df.attrs.get("errors_df", pd.DataFrame())
    race_meta_df = results_raw_df.attrs.get("race_meta_df", pd.DataFrame())
    payout_detail_df = results_raw_df.attrs.get("payout_detail_df", pd.DataFrame())

    fetch_summary_df = pd.DataFrame([
        {
            "target": "racelist_final",
            "jcd": jcd,
            "start_hd": "",
            "prev_hd": "",
            "final_hd": final_hd,
            "rows": len(racelist_df),
            "error_rows": len(racelist_errors_df),
            "is_empty": racelist_df.empty,
        },
        {
            "target": "results_raw",
            "jcd": jcd,
            "start_hd": start_hd,
            "prev_hd": prev_hd,
            "final_hd": "",
            "rows": len(results_raw_df),
            "error_rows": len(results_errors_df),
            "is_empty": results_raw_df.empty,
        },
        {
            "target": "summary",
            "jcd": jcd,
            "start_hd": start_hd,
            "prev_hd": prev_hd,
            "final_hd": "",
            "rows": len(summary_df),
            "error_rows": 0,
            "is_empty": summary_df.empty,
        },
    ])

    debug_fetch_summary_path = output_dir / f"debug_fetch_summary_jcd{jcd}_{final_hd}.csv"
    fetch_summary_df.to_csv(debug_fetch_summary_path, index=False, encoding="utf-8-sig")
    debug_files.append(debug_fetch_summary_path)

    debug_racelist_errors_path = output_dir / f"debug_racelist_errors_jcd{jcd}_{final_hd}.csv"
    racelist_errors_df.to_csv(debug_racelist_errors_path, index=False, encoding="utf-8-sig")
    debug_files.append(debug_racelist_errors_path)

    debug_results_errors_path = output_dir / f"debug_results_errors_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    results_errors_df.to_csv(debug_results_errors_path, index=False, encoding="utf-8-sig")
    debug_files.append(debug_results_errors_path)

    if debug_mode:
        debug_raw_path = output_dir / f"debug_race_results_raw_jcd{jcd}_{start_hd}_{prev_hd}.csv"
        results_raw_df.to_csv(debug_raw_path, index=False, encoding="utf-8-sig")
        debug_files.append(debug_raw_path)

        debug_meta_path = output_dir / f"debug_race_meta_jcd{jcd}_{start_hd}_{prev_hd}.csv"
        race_meta_df.to_csv(debug_meta_path, index=False, encoding="utf-8-sig")
        debug_files.append(debug_meta_path)

        debug_payout_path = output_dir / f"debug_payout_detail_jcd{jcd}_{start_hd}_{prev_hd}.csv"
        payout_detail_df.to_csv(debug_payout_path, index=False, encoding="utf-8-sig")
        debug_files.append(debug_payout_path)

    st.success("ファイル作成が完了しました。")

    st.subheader("チェック結果")

    st.write("### 出走表")
    for msg in validate_racelist_detail(racelist_df):
        st.write(msg)

    st.write("### 結果raw")
    for msg in validate_results_raw(results_raw_df):
        st.write(msg)

    st.write("### 取得サマリ")
    st.dataframe(fetch_summary_df)

    if not racelist_errors_df.empty:
        st.write("### 出走表エラー")
        st.dataframe(racelist_errors_df.head(30))

    if not results_errors_df.empty:
        st.write("### 結果エラー")
        st.dataframe(results_errors_df.head(30))

    st.subheader("作成ファイル")

    st.write(racelist_path.name)
    st.write(summary_path.name)
    st.write(readme_path.name)
    st.write(tenkai_path.name)

    zip_path = output_dir / f"boatrace_forecast_files_jcd{jcd}_{final_hd}.zip"

    zip_files = [
        racelist_path,
        summary_path,
        readme_path,
        tenkai_path,
    ]

    if debug_mode or racelist_df.empty or results_raw_df.empty or summary_df.empty:
        zip_files += debug_files

    make_zip(zip_path, zip_files)

    with open(zip_path, "rb") as f:
        st.download_button(
            label="4ファイルzipをダウンロード",
            data=f,
            file_name=zip_path.name,
            mime="application/zip",
        )

    prompt = build_chatgpt_prompt(jcd, start_hd, prev_hd, final_hd)

    st.subheader("ChatGPT貼り付け用プロンプト")
    st.caption("zip内の4ファイルを添付したうえで、この文章をChatGPTに貼ってください。")
    st.text_area(
        "プロンプト",
        prompt,
        height=420,
    )
