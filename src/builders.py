from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .parser import parse_racelist, parse_raceresult
from .scraper import assert_no_leak, fetch_html, make_url


def daterange(start_yyyymmdd: str, end_yyyymmdd: str):
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    cur = start
    while cur <= end:
        yield cur.strftime("%Y%m%d")
        cur += timedelta(days=1)


def build_racelist_detail(jcd: str, final_hd: str, debug_dir: Path | None = None) -> pd.DataFrame:
    dfs = []
    jcd = str(jcd).zfill(2)
    for rno in range(1, 13):
        assert_no_leak("racelist", is_final_day=True)
        url = make_url("racelist", rno, jcd, final_hd)
        fetch = fetch_html(url)
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"racelist_{final_hd}_{jcd}_{rno:02d}.html").write_text(fetch.html, encoding="utf-8")
        df = parse_racelist(fetch.html, race_date=final_hd, jcd=jcd, rno=rno, url=url)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def build_results_raw(jcd: str, start_hd: str, prev_hd: str, debug_dir: Path | None = None) -> pd.DataFrame:
    dfs = []
    jcd = str(jcd).zfill(2)
    for hd in daterange(start_hd, prev_hd):
        for rno in range(1, 13):
            assert_no_leak("raceresult", is_final_day=False)
            url = make_url("raceresult", rno, jcd, hd)
            try:
                fetch = fetch_html(url)
            except Exception as e:
                print(f"[WARN] fetch failed: {url}: {e}")
                continue
            if debug_dir:
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / f"raceresult_{hd}_{jcd}_{rno:02d}.html").write_text(fetch.html, encoding="utf-8")
            df = parse_raceresult(fetch.html, race_date=hd, jcd=jcd, rno=rno, url=url)
            if not df.empty:
                dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def build_racer_course_style_summary(results_raw: pd.DataFrame) -> pd.DataFrame:
    if results_raw.empty:
        return pd.DataFrame()
    df = results_raw.copy()
    for c in ["st", "rank", "course", "frame"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["is_1st"] = df["rank"].eq(1)
    df["is_top2"] = df["rank"].le(2)
    df["is_top3"] = df["rank"].le(3)
    df["is_last"] = df["rank"].eq(6)
    df["is_late_020"] = df["st"].ge(0.20)
    df["is_late_025"] = df["st"].ge(0.25)
    df["is_flying"] = df["st"].lt(0)

    # レース内ST順位・内外比較
    df["st_rank"] = df.groupby("race_id")["st"].rank(method="min", ascending=True)
    df["st_diff_vs_race_avg"] = df["st"] - df.groupby("race_id")["st"].transform("mean")
    df["st_diff_vs_fastest"] = df["st"] - df.groupby("race_id")["st"].transform("min")

    inner = df[["race_id", "course", "st"]].copy()
    inner["course"] = inner["course"] + 1
    inner = inner.rename(columns={"st": "inner_st"})
    df = df.merge(inner, on=["race_id", "course"], how="left")
    df["st_diff_vs_inner"] = df["st"] - df["inner_st"]
    df["faster_than_inner"] = df["st_diff_vs_inner"].lt(0)
    df["much_faster_than_inner_003"] = df["st_diff_vs_inner"].le(-0.03)
    df["much_faster_than_inner_005"] = df["st_diff_vs_inner"].le(-0.05)

    outer = df[["race_id", "course", "st"]].copy()
    outer["course"] = outer["course"] - 1
    outer = outer.rename(columns={"st": "outer_st"})
    df = df.merge(outer, on=["race_id", "course"], how="left")
    df["st_diff_vs_outer"] = df["st"] - df["outer_st"]
    df["faster_than_outer"] = df["st_diff_vs_outer"].lt(0)

    for k in ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]:
        df[k] = df["decision"].astype(str).eq(k) & df["is_1st"]

    g = df.groupby(["racer_id", "racer_name", "course"], dropna=False)
    summary = g.agg(
        entries=("race_id", "count"),
        avg_st=("st", "mean"),
        median_st=("st", "median"),
        std_st=("st", "std"),
        min_st=("st", "min"),
        max_st=("st", "max"),
        st_rank_avg=("st_rank", "mean"),
        st_rank_median=("st_rank", "median"),
        st_rank1_count=("st_rank", lambda s: int((s == 1).sum())),
        st_rank2in_count=("st_rank", lambda s: int((s <= 2).sum())),
        st_rank3in_count=("st_rank", lambda s: int((s <= 3).sum())),
        st_last_count=("st_rank", lambda s: int((s == 6).sum())),
        st_diff_vs_race_avg_avg=("st_diff_vs_race_avg", "mean"),
        st_diff_vs_fastest_avg=("st_diff_vs_fastest", "mean"),
        st_diff_vs_inner_avg=("st_diff_vs_inner", "mean"),
        faster_than_inner_count=("faster_than_inner", "sum"),
        much_faster_than_inner_003_count=("much_faster_than_inner_003", "sum"),
        much_faster_than_inner_005_count=("much_faster_than_inner_005", "sum"),
        st_diff_vs_outer_avg=("st_diff_vs_outer", "mean"),
        faster_than_outer_count=("faster_than_outer", "sum"),
        avg_finish=("rank", "mean"),
        median_finish=("rank", "median"),
        std_finish=("rank", "std"),
        win_count=("is_1st", "sum"),
        top2_count=("is_top2", "sum"),
        top3_count=("is_top3", "sum"),
        last_count=("is_last", "sum"),
        st_late_020_count=("is_late_020", "sum"),
        st_late_025_count=("is_late_025", "sum"),
        flying_count=("is_flying", "sum"),
        frame_avg=("frame", "mean"),
        frame_mode=("frame", lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan),
        races=("race_id", lambda s: " / ".join(map(str, sorted(set(s))))),
        **{k: (k, "sum") for k in ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]},
    ).reset_index()

    summary["win_rate"] = summary["win_count"] / summary["entries"]
    summary["top2_rate"] = summary["top2_count"] / summary["entries"]
    summary["top3_rate"] = summary["top3_count"] / summary["entries"]
    summary["last_rate"] = summary["last_count"] / summary["entries"]
    summary["st_rank1_rate"] = summary["st_rank1_count"] / summary["entries"]
    summary["st_rank2in_rate"] = summary["st_rank2in_count"] / summary["entries"]
    summary["st_rank3in_rate"] = summary["st_rank3in_count"] / summary["entries"]
    summary["st_last_rate"] = summary["st_last_count"] / summary["entries"]
    summary["st_late_020_rate"] = summary["st_late_020_count"] / summary["entries"]
    summary["st_late_025_rate"] = summary["st_late_025_count"] / summary["entries"]
    summary["flying_rate"] = summary["flying_count"] / summary["entries"]
    summary["faster_than_inner_rate"] = summary["faster_than_inner_count"] / summary["entries"]
    summary["much_faster_than_inner_003_rate"] = summary["much_faster_than_inner_003_count"] / summary["entries"]
    summary["much_faster_than_inner_005_rate"] = summary["much_faster_than_inner_005_count"] / summary["entries"]
    summary["faster_than_outer_rate"] = summary["faster_than_outer_count"] / summary["entries"]

    kimarite_cols = ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]
    summary["win_kimarite_total"] = summary[kimarite_cols].sum(axis=1)
    summary["main_win_kimarite"] = summary[kimarite_cols].idxmax(axis=1)
    summary.loc[summary["win_kimarite_total"].eq(0), "main_win_kimarite"] = np.nan

    # 予想補助スコア。厳密なモデルではなくChatGPT用の特徴量。
    summary["st_speed_score"] = (0.25 - summary["avg_st"]).clip(lower=0, upper=0.25) / 0.25
    summary["st_stability_score"] = (0.12 - summary["std_st"].fillna(0.12)).clip(lower=0, upper=0.12) / 0.12
    summary["st_top_score"] = summary["st_rank2in_rate"].fillna(0)
    summary["course_result_score"] = summary["top3_rate"].fillna(0)
    summary["attack_score"] = (
        summary["much_faster_than_inner_003_rate"].fillna(0) * 0.4
        + summary["st_rank2in_rate"].fillna(0) * 0.3
        + summary[["まくり", "まくり差し"]].sum(axis=1).fillna(0).clip(upper=1) * 0.3
    )
    summary["inner_reliability_score"] = np.where(
        summary["course"].eq(1),
        summary["top3_rate"].fillna(0) * 0.5 + summary["st_rank3in_rate"].fillna(0) * 0.5,
        np.nan,
    )
    summary["outside_pickup_score"] = np.where(
        summary["course"].ge(5),
        summary["top3_rate"].fillna(0) * 0.7 + (1 - summary["last_rate"].fillna(1)) * 0.3,
        np.nan,
    )

    summary["course_style_label"] = "通常"
    summary.loc[summary["entries"].lt(3), "course_style_label"] = "サンプル少"
    summary.loc[(summary["course"].eq(1)) & (summary["inner_reliability_score"].ge(0.65)), "course_style_label"] = "イン安定"
    summary.loc[(summary["course"].between(2, 4)) & (summary["attack_score"].ge(0.45)), "course_style_label"] = "攻め候補"
    summary.loc[(summary["course"].ge(5)) & (summary["outside_pickup_score"].ge(0.55)), "course_style_label"] = "外枠拾い"

    # サンプルCSVに近い列順に並べる
    front_cols = [
        "racer_id", "racer_name", "course", "entries", "course_style_label",
        "avg_st", "median_st", "std_st", "min_st", "max_st",
        "st_rank_avg", "st_rank1_rate", "st_rank2in_rate", "st_rank3in_rate", "st_last_rate",
        "st_late_020_rate", "st_late_025_rate", "flying_rate",
        "st_diff_vs_inner_avg", "faster_than_inner_rate", "much_faster_than_inner_003_rate", "much_faster_than_inner_005_rate",
        "st_diff_vs_outer_avg", "faster_than_outer_rate",
        "avg_finish", "win_rate", "top2_rate", "top3_rate", "last_rate",
        "attack_score", "inner_reliability_score", "outside_pickup_score",
        "st_speed_score", "st_stability_score", "st_top_score", "course_result_score", "main_win_kimarite",
    ]
    rest_cols = [c for c in summary.columns if c not in front_cols]
    return summary[front_cols + rest_cols]
