from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.builders import build_racelist_detail, build_results_raw, build_racer_course_style_summary
from src.prompt_builder import build_chatgpt_prompt
from src.validators import validate_join_coverage, validate_racelist_detail, validate_results_raw
from src.zip_utils import make_zip


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jcd", required=True, help="場コード 例: 14")
    p.add_argument("--start", required=True, help="初日 YYYYMMDD")
    p.add_argument("--prev", required=True, help="前日 YYYYMMDD")
    p.add_argument("--final", required=True, help="最終日 YYYYMMDD")
    p.add_argument("--debug-html", action="store_true", help="取得HTMLをoutputs配下に保存")
    args = p.parse_args()

    jcd = str(args.jcd).zfill(2)
    out_dir = Path("outputs") / f"jcd{jcd}_{args.final}"
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = out_dir / "debug_html" if args.debug_html else None

    print("[1/4] 最終日の出走表を取得")
    racelist_df = build_racelist_detail(jcd, args.final, debug_dir=debug_dir)
    racelist_path = out_dir / f"racelist_detail_jcd{jcd}_{args.final}.csv"
    racelist_df.to_csv(racelist_path, index=False, encoding="utf-8-sig")

    print("[2/4] 初日〜前日の結果を取得")
    results_raw_df = build_results_raw(jcd, args.start, args.prev, debug_dir=debug_dir)
    raw_path = out_dir / f"race_results_raw_jcd{jcd}_{args.start}_{args.prev}.csv"
    results_raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")

    print("[3/4] 選手別・コース別傾向を集計")
    summary_df = build_racer_course_style_summary(results_raw_df)
    summary_path = out_dir / f"racer_course_style_summary_jcd{jcd}_{args.start}_{args.prev}.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    print("[4/4] 固定ファイル・プロンプト・zipを作成")
    readme_path = out_dir / "README.md"
    tenkai_path = out_dir / "展開.txt"
    shutil.copy(Path("fixed_files") / "README.md", readme_path)
    shutil.copy(Path("fixed_files") / "展開.txt", tenkai_path)

    prompt_path = out_dir / f"chatgpt_prompt_jcd{jcd}_{args.final}.txt"
    prompt_path.write_text(build_chatgpt_prompt(jcd, args.start, args.prev, args.final), encoding="utf-8")

    zip_path = out_dir / f"boatrace_forecast_files_jcd{jcd}_{args.final}.zip"
    make_zip(zip_path, [racelist_path, summary_path, readme_path, tenkai_path])

    print("\n出走表チェック")
    print("\n".join(validate_racelist_detail(racelist_df)))
    print("\n結果rawチェック")
    print("\n".join(validate_results_raw(results_raw_df)))
    print("\n結合カバレッジ")
    print("\n".join(validate_join_coverage(racelist_df, summary_df)))
    print(f"\nZIP: {zip_path}")
    print(f"PROMPT: {prompt_path}")


if __name__ == "__main__":
    main()
