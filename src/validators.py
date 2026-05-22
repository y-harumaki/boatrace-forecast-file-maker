from __future__ import annotations

import pandas as pd


def validate_dates(start_hd: str, prev_hd: str, final_hd: str) -> list[str]:
    msgs = []
    if not (start_hd <= prev_hd < final_hd):
        msgs.append("[NG] 日付条件が不正です。初日 <= 前日 < 最終日 にしてください。")
    else:
        msgs.append("[OK] 日付条件: 初日 <= 前日 < 最終日")
    return msgs


def validate_racelist_detail(df: pd.DataFrame) -> list[str]:
    msgs = []
    msgs.append(f"出走表行数: {len(df)}")
    if len(df) == 72:
        msgs.append("[OK] 出走表は 12R × 6艇 = 72行")
    else:
        msgs.append(f"[WARN] 出走表が72行ではありません: {len(df)}")

    required = ["race_date", "jcd", "rno", "frame", "racer_id", "racer_name"]
    for col in required:
        if col not in df.columns:
            msgs.append(f"[NG] 必須列がありません: {col}")

    if {"rno", "frame"}.issubset(df.columns):
        for rno in range(1, 13):
            sub = df[df["rno"] == rno]
            frames = sorted(pd.to_numeric(sub["frame"], errors="coerce").dropna().astype(int).unique().tolist())
            if frames == [1, 2, 3, 4, 5, 6]:
                msgs.append(f"[OK] {rno}R: 1〜6号艇あり")
            else:
                msgs.append(f"[WARN] {rno}R: 枠番が不完全 {frames}")

    for col in ["racer_id", "racer_name"]:
        if col in df.columns:
            miss = int(df[col].isna().sum())
            if miss == 0:
                msgs.append(f"[OK] {col} 欠損なし")
            else:
                msgs.append(f"[WARN] {col} 欠損: {miss}")
    return msgs


def validate_results_raw(df: pd.DataFrame) -> list[str]:
    msgs = []
    msgs.append(f"結果raw行数: {len(df)}")
    if df.empty:
        msgs.append("[NG] 結果rawが空です。公式サイト取得またはparserを確認してください。")
        return msgs
    if "race_id" in df.columns:
        msgs.append(f"取得レース数: {df['race_id'].nunique()}")
    for col, name in [("st", "ST"), ("course", "進入コース"), ("rank", "着順"), ("decision", "決まり手")]:
        if col in df.columns:
            miss = int(df[col].isna().sum())
            msgs.append(f"{name} 欠損: {miss}")
        else:
            msgs.append(f"[WARN] {name} 列がありません: {col}")
    return msgs


def validate_join_coverage(racelist_df: pd.DataFrame, summary_df: pd.DataFrame) -> list[str]:
    msgs = []
    if racelist_df.empty or summary_df.empty or "racer_id" not in racelist_df.columns or "racer_id" not in summary_df.columns:
        msgs.append("[WARN] 結合カバレッジを確認できません。")
        return msgs
    final_racers = set(pd.to_numeric(racelist_df["racer_id"], errors="coerce").dropna().astype(int))
    summary_racers = set(pd.to_numeric(summary_df["racer_id"], errors="coerce").dropna().astype(int))
    covered = final_racers & summary_racers
    missing = final_racers - summary_racers
    msgs.append(f"最終日出走選手数: {len(final_racers)}")
    msgs.append(f"今節集計あり: {len(covered)}")
    msgs.append(f"今節集計なし: {len(missing)}")
    if missing:
        names = racelist_df[pd.to_numeric(racelist_df["racer_id"], errors="coerce").isin(missing)][["rno", "frame", "racer_id", "racer_name"]]
        miss_txt = "; ".join(
            f"{int(r.rno)}R-{int(r.frame)}号艇 {int(r.racer_id)} {r.racer_name}" for r in names.itertuples()
        )
        msgs.append(f"[INFO] 集計なし選手: {miss_txt}")
    return msgs
