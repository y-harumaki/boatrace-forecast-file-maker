from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import zipfile

import pandas as pd

from src.builders import (
    build_racelist_detail,
    build_results_raw,
    build_racer_course_style_summary,
    add_reliability_flags,
)


def normalize_jcd(jcd: str) -> str:
    return str(jcd).zfill(2)


def validate_dates(start_hd: str, prev_hd: str, final_hd: str) -> None:
    if not (len(start_hd) == len(prev_hd) == len(final_hd) == 8):
        raise ValueError("日付は YYYYMMDD 形式で指定してください。")

    if not (start_hd <= prev_hd < final_hd):
        raise ValueError(
            f"日付条件が不正です: start={start_hd}, prev={prev_hd}, final={final_hd}"
        )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def make_zip(zip_path: Path, files: list[Path]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            if p.exists():
                zf.write(p, arcname=p.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jcd", required=True)
    parser.add_argument("--start-date", required=True, help="YYYYMMDD")
    parser.add_argument("--prev-date", required=True, help="YYYYMMDD")
    parser.add_argument("--final-date", required=True, help="YYYYMMDD")

    args = parser.parse_args()

    jcd = normalize_jcd(args.jcd)
    start_hd = args.start_date
    prev_hd = args.prev_date
    final_hd = args.final_date

    validate_dates(start_hd, prev_hd, final_hd)

    out_dir = Path("outputs") / "github_action" / f"jcd{jcd}_{final_hd}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("========================================")
    print("BOATRACE forecast file maker")
    print("========================================")
    print(f"jcd      : {jcd}")
    print(f"start_hd : {start_hd}")
    print(f"prev_hd  : {prev_hd}")
    print(f"final_hd : {final_hd}")
    print("========================================")

    # =====================================================
    # 1. 最終日 出走表
    # =====================================================
    print("[1/4] build racelist detail...")
    racelist_df = build_racelist_detail(jcd, final_hd)

    racelist_path = out_dir / f"racelist_detail_jcd{jcd}_{final_hd}.csv"
    save_csv(racelist_df, racelist_path)

    print("racelist_df shape:", racelist_df.shape)

    racelist_errors_df = racelist_df.attrs.get("errors_df", pd.DataFrame())
    racelist_errors_path = out_dir / f"debug_racelist_errors_jcd{jcd}_{final_hd}.csv"
    save_csv(racelist_errors_df, racelist_errors_path)

    # =====================================================
    # 2. 初日〜前日 結果raw
    # =====================================================
    print("[2/4] build results raw...")
    results_raw_df = build_results_raw(jcd, start_hd, prev_hd)

    results_raw_path = out_dir / f"debug_race_results_raw_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    save_csv(results_raw_df, results_raw_path)

    print("results_raw_df shape:", results_raw_df.shape)

    results_errors_df = results_raw_df.attrs.get("errors_df", pd.DataFrame())
    results_errors_path = out_dir / f"debug_results_errors_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    save_csv(results_errors_df, results_errors_path)

    race_meta_df = results_raw_df.attrs.get("race_meta_df", pd.DataFrame())
    race_meta_path = out_dir / f"debug_race_meta_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    save_csv(race_meta_df, race_meta_path)

    payout_detail_df = results_raw_df.attrs.get("payout_detail_df", pd.DataFrame())
    payout_detail_path = out_dir / f"debug_payout_detail_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    save_csv(payout_detail_df, payout_detail_path)

    # =====================================================
    # 3. 選手別・コース別集計
    # =====================================================
    print("[3/4] build racer course style summary...")

    # pandas merge時に DataFrame.attrs 内の DataFrame 同士を比較して落ちることがある。
    # 集計処理に attrs は不要なので、attrs を消したコピーを渡す。
    summary_input_df = results_raw_df.copy()
    summary_input_df.attrs.clear()

    summary_df = build_racer_course_style_summary(summary_input_df)
    summary_df = add_reliability_flags(summary_df)

    summary_path = out_dir / f"racer_course_style_summary_jcd{jcd}_{start_hd}_{prev_hd}.csv"
    save_csv(summary_df, summary_path)

    print("summary_df shape:", summary_df.shape)

    # =====================================================
    # 4. 固定ファイル
    # =====================================================
    print("[4/4] copy fixed files...")

    readme_src = Path("fixed_files") / "README.md"
    tenkai_candidates = [
        Path("fixed_files") / "展開.txt",
        Path("fixed_files") / "tenkai.txt",
    ]

    if not readme_src.exists():
        raise FileNotFoundError("fixed_files/README.md が見つかりません。")

    tenkai_src = None
    for p in tenkai_candidates:
        if p.exists():
            tenkai_src = p
            break

    if tenkai_src is None:
        raise FileNotFoundError(
            "fixed_files/展開.txt または fixed_files/tenkai.txt が見つかりません。"
        )

    readme_path = out_dir / "README.md"
    tenkai_path = out_dir / "展開.txt"

    shutil.copy(readme_src, readme_path)
    shutil.copy(tenkai_src, tenkai_path)

    # =====================================================
    # 5. サマリ
    # =====================================================
    fetch_summary_df = pd.DataFrame(
        [
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
        ]
    )

    fetch_summary_path = out_dir / f"debug_fetch_summary_jcd{jcd}_{final_hd}.csv"
    save_csv(fetch_summary_df, fetch_summary_path)

    print("fetch summary:")
    print(fetch_summary_df.to_string(index=False))

    # =====================================================
    # 6. ChatGPT添付用zip
    # =====================================================
    zip_path = out_dir / f"boatrace_forecast_files_jcd{jcd}_{final_hd}.zip"

    zip_files = [
        racelist_path,
        summary_path,
        readme_path,
        tenkai_path,
    ]

    # 空の場合はデバッグも同梱
    if racelist_df.empty or results_raw_df.empty or summary_df.empty:
        zip_files += [
            fetch_summary_path,
            racelist_errors_path,
            results_errors_path,
            results_raw_path,
            race_meta_path,
            payout_detail_path,
        ]

    make_zip(zip_path, zip_files)

    print("========================================")
    print("DONE")
    print("zip:", zip_path)
    print("========================================")

    if racelist_df.empty:
        print("[WARN] racelist_df is empty")
    if results_raw_df.empty:
        print("[WARN] results_raw_df is empty")
    if summary_df.empty:
        print("[WARN] summary_df is empty")


if __name__ == "__main__":
    main()
