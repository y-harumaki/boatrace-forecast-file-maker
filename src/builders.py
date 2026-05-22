from __future__ import annotations

import re
import time
import random
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup, FeatureNotFound


# =========================================================
# 0. 共通設定
# =========================================================

try:
    BeautifulSoup("<html></html>", "lxml")
    BS4_PARSER = "lxml"
except FeatureNotFound:
    BS4_PARSER = "html.parser"


SLEEP_SEC = 0.25
TIMEOUT_CONNECT = 5
TIMEOUT_READ = 30
MAX_RETRY = 2
MIN_ENTRIES_FOR_LABEL = 3

MOVE_WORDS = ["まくり差し", "まくり", "差し", "逃げ", "抜き", "恵まれ"]
PAYOUT_TYPES = {"3連単", "3連複", "2連単", "2連複", "拡連複", "単勝", "複勝"}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "close",
})


# =========================================================
# 1. 共通ユーティリティ
# =========================================================

def norm_text(x) -> str:
    if x is None:
        return ""
    s = unicodedata.normalize("NFKC", str(x))
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_int_safe(x):
    s = norm_text(x).replace(",", "")
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return None


def parse_float_safe(x):
    s = norm_text(x).replace(",", "")
    if s in {"", "-", "－"}:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def parse_money(x):
    s = norm_text(x)
    m = re.search(r"([0-9,]+)", s)
    return int(m.group(1).replace(",", "")) if m else None


def parse_st(x):
    """
    .14  -> 0.14
    F.01 -> -0.01
    L.01 -> 1.01
    """
    s = norm_text(x).replace(" ", "")
    m = re.search(r"(F|L)?\.?(\d{2})", s)
    if not m:
        return None, ""

    status = m.group(1) or ""
    val = float("0." + m.group(2))

    if status == "F":
        val = -val
    elif status == "L":
        val = 1 + val

    return val, status


def table_text(table) -> str:
    return norm_text(table.get_text(" ", strip=True))


def find_table_by_headers(soup: BeautifulSoup, required: list[str]):
    for table in soup.find_all("table"):
        heads = [
            norm_text(x.get_text(" ", strip=True))
            for x in table.find_all("th")
        ]
        text = table_text(table)
        if all(r in heads or r in text for r in required):
            return table
    return None


def daterange(start_yyyymmdd: str, end_yyyymmdd: str):
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d")

    cur = start
    while cur <= end:
        yield cur.strftime("%Y%m%d")
        cur += timedelta(days=1)


def q25(s):
    return s.quantile(0.25)


def q75(s):
    return s.quantile(0.75)


def main_value(s):
    s = s.dropna().astype(str)
    s = s[s != ""]
    if len(s) == 0:
        return None
    return s.value_counts().index[0]


def get_cell_text(td) -> str:
    return norm_text(td.get_text(" ", strip=True)) if td is not None else ""


def split_lines_from_cell(td):
    if td is None:
        return []

    html = str(td)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    soup = BeautifulSoup(html, BS4_PARSER)
    text = soup.get_text("\n")
    lines = [norm_text(x) for x in text.splitlines()]
    return [x for x in lines if x != ""]


# =========================================================
# 2. ページ取得
# =========================================================

def fetch_result_html(hd: str, jcd: str, rno: int, max_retry=MAX_RETRY):
    url = (
        "https://www.boatrace.jp/owpc/pc/race/raceresult"
        f"?rno={int(rno)}&jcd={int(jcd):02d}&hd={hd}"
    )

    referer = (
        "https://www.boatrace.jp/owpc/pc/race/raceindex"
        f"?jcd={int(jcd):02d}&hd={hd}"
    )

    last_error = None

    for attempt in range(max_retry):
        try:
            res = SESSION.get(
                url,
                timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
                headers={"Referer": referer},
            )
            res.encoding = "utf-8"

            if res.status_code == 200 and len(res.text) > 1000:
                return res.text, url, None

            last_error = f"status={res.status_code}, len={len(res.text)}"

        except Exception as e:
            last_error = repr(e)

        if attempt < max_retry - 1:
            time.sleep(1.0)

    return None, url, last_error


def fetch_racelist_html(hd: str, jcd: str, rno: int, max_retry=MAX_RETRY):
    url = (
        "https://www.boatrace.jp/owpc/pc/race/racelist"
        f"?rno={int(rno)}&jcd={int(jcd):02d}&hd={hd}"
    )

    referer = (
        "https://www.boatrace.jp/owpc/pc/race/raceindex"
        f"?jcd={int(jcd):02d}&hd={hd}"
    )

    last_error = None

    for attempt in range(max_retry):
        try:
            res = SESSION.get(
                url,
                timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
                headers={"Referer": referer},
            )
            res.encoding = "utf-8"

            if res.status_code == 200 and len(res.text) > 1000:
                return res.text, url, None

            last_error = f"status={res.status_code}, len={len(res.text)}"

        except Exception as e:
            last_error = repr(e)

        if attempt < max_retry - 1:
            time.sleep(1.0)

    return None, url, last_error


# =========================================================
# 3. HTML切り出し
# =========================================================

def extract_result_main_html(html: str) -> str:
    anchors = [
        "contentsFrame1_inner",
        "table1_result",
        "スタート情報",
        "水面気象情報",
        "勝式",
        "決まり手",
    ]

    starts = [html.find(a) for a in anchors]
    starts = [s for s in starts if s != -1]

    if not starts:
        return html

    start = max(0, min(starts) - 3000)

    end_candidates = [
        html.find("<footer", start),
        html.find("</main>", start),
        html.find('class="l-footer"', start),
    ]
    end_candidates = [x for x in end_candidates if x != -1]

    end = min(end_candidates) if end_candidates else len(html)
    return html[start:end]


def extract_racelist_main_html(html: str) -> str:
    anchors = [
        "is-tableFixed__3rdadd",
        "ボートレーサー",
        "全国",
        "当地",
        "モーター",
        "今節成績",
    ]

    starts = [html.find(a) for a in anchors]
    starts = [s for s in starts if s != -1]

    if not starts:
        return html

    start = max(0, min(starts) - 3000)

    end_candidates = [
        html.find("<footer", start),
        html.find("</main>", start),
        html.find('class="l-footer"', start),
    ]
    end_candidates = [x for x in end_candidates if x != -1]

    end = min(end_candidates) if end_candidates else len(html)
    return html[start:end]


# =========================================================
# 4. 結果ページ parser
# =========================================================

def parse_result_table(soup: BeautifulSoup, hd: str, jcd: str, rno: int, url: str):
    table = find_table_by_headers(
        soup,
        ["着", "枠", "ボートレーサー", "レースタイム"]
    )

    if table is None:
        return pd.DataFrame()

    rows = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 4:
            continue

        finish_label = norm_text(tds[0].get_text(" ", strip=True))
        frame = parse_int_safe(tds[1].get_text(" ", strip=True))

        racer_cell = tds[2]
        racer_text = norm_text(racer_cell.get_text(" ", strip=True))

        rid_span = racer_cell.find("span", class_=lambda c: c and "is-fs12" in c)
        name_span = racer_cell.find("span", class_=lambda c: c and "is-fs18" in c)

        racer_id = norm_text(rid_span.get_text(" ", strip=True)) if rid_span else None
        if not racer_id:
            m = re.search(r"\b(\d{4})\b", racer_text)
            racer_id = m.group(1) if m else None

        racer_name = norm_text(name_span.get_text(" ", strip=True)) if name_span else None
        if not racer_name:
            racer_name = norm_text(re.sub(r"^\d{4}\s*", "", racer_text))

        race_time = norm_text(tds[3].get_text(" ", strip=True)) or None
        finish_num = parse_int_safe(finish_label)

        rows.append({
            "race_date": hd,
            "jcd": f"{int(jcd):02d}",
            "rno": int(rno),
            "race_no": int(rno),
            "race_id": f"{hd}_{int(jcd):02d}_{int(rno):02d}",
            "url": url,
            "finish_label": finish_label,
            "finish_num": finish_num,
            "rank": finish_num,
            "frame": frame,
            "frame_no": frame,
            "racer_id": racer_id,
            "racer_name": racer_name,
            "race_time": race_time,
        })

    return pd.DataFrame(rows)


def parse_start_table(soup: BeautifulSoup):
    table = find_table_by_headers(soup, ["スタート情報"])

    if table is None:
        return pd.DataFrame(columns=[
            "frame", "course", "st", "st_status", "start_move"
        ])

    rows = []
    course = 0

    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue

        td = tds[0]
        text = norm_text(td.get_text(" ", strip=True))

        span = td.select_one(".table1_boatImage1Number")

        if span is None and not re.search(r"(F|L)?\.?\d{2}", text):
            continue

        course += 1

        frame = parse_int_safe(span.get_text(" ", strip=True)) if span else None

        if frame is None:
            m = re.match(r"([1-6])\b", text)
            frame = int(m.group(1)) if m else course

        st, st_status = parse_st(text)

        start_move = ""
        for w in MOVE_WORDS:
            if w in text:
                start_move = w
                break

        rows.append({
            "frame": frame,
            "course": course,
            "st": st,
            "st_status": st_status,
            "start_move": start_move,
        })

    return pd.DataFrame(rows)


def parse_payout_table(soup: BeautifulSoup):
    table = find_table_by_headers(
        soup,
        ["勝式", "組番", "払戻金", "人気"]
    )

    if table is None:
        return pd.DataFrame(columns=[
            "bet_type", "combo", "payout_yen", "popularity"
        ])

    rows = []
    current_type = None

    for tr in table.find_all("tr"):
        cells = [
            norm_text(td.get_text(" ", strip=True))
            for td in tr.find_all("td", recursive=False)
        ]
        cells = [c for c in cells if c != ""]

        if not cells:
            continue

        if cells[0] in PAYOUT_TYPES:
            current_type = cells[0]
            rest = cells[1:]
        else:
            if current_type is None:
                continue
            rest = cells

        if not rest:
            continue

        combo = rest[0] if len(rest) >= 1 else None
        payout_yen = parse_money(rest[1]) if len(rest) >= 2 else None
        popularity = parse_int_safe(rest[2]) if len(rest) >= 3 else None

        if combo is None and payout_yen is None:
            continue

        rows.append({
            "bet_type": current_type,
            "combo": combo,
            "payout_yen": payout_yen,
            "popularity": popularity,
        })

    return pd.DataFrame(rows)


def parse_kimarite(soup: BeautifulSoup):
    table = find_table_by_headers(soup, ["決まり手"])

    if table is None:
        return None

    values = []
    for tr in table.find_all("tr"):
        cells = [
            norm_text(x.get_text(" ", strip=True))
            for x in tr.find_all(["th", "td"])
        ]
        values.extend([x for x in cells if x])

    values = [x for x in values if x != "決まり手"]
    return values[0] if values else None


def parse_weather(soup: BeautifulSoup):
    out = {
        "weather": None,
        "temperature_c": None,
        "wind_speed_m": None,
        "water_temperature_c": None,
        "wave_height_cm": None,
        "wind_direction_class": None,
        "stand_side": None,
    }

    w = soup.select_one(".weather1")
    if w is None:
        return out

    weather_unit = w.select_one(
        ".weather1_bodyUnit.is-weather .weather1_bodyUnitLabelTitle"
    )
    if weather_unit:
        out["weather"] = norm_text(weather_unit.get_text(" ", strip=True))

    for unit in w.select(".weather1_bodyUnit"):
        cls = unit.get("class") or []

        label = unit.select_one(".weather1_bodyUnitLabelTitle")
        data = unit.select_one(".weather1_bodyUnitLabelData")

        label_text = norm_text(label.get_text(" ", strip=True)) if label else ""
        data_text = norm_text(data.get_text(" ", strip=True)) if data else ""

        if "is-direction" in cls and label_text == "気温":
            out["temperature_c"] = parse_float_safe(data_text)
        elif "is-wind" in cls:
            out["wind_speed_m"] = parse_float_safe(data_text)
        elif "is-waterTemperature" in cls:
            out["water_temperature_c"] = parse_float_safe(data_text)
        elif "is-wave" in cls:
            out["wave_height_cm"] = parse_float_safe(data_text)
        elif "is-windDirection" in cls:
            p = unit.select_one(".weather1_bodyUnitImage")
            if p:
                wind_classes = [
                    c for c in (p.get("class") or [])
                    if c.startswith("is-wind")
                ]
                out["wind_direction_class"] = wind_classes[0] if wind_classes else None

    stand = w.select_one(".weather1_stand")
    if stand:
        out["stand_side"] = norm_text(stand.get_text(" ", strip=True))

    return out


def parse_race_header(soup: BeautifulSoup):
    place = None
    title = None
    race_title = None
    distance_m = None

    place_img = soup.select_one(".heading2_area img")
    if place_img and place_img.get("alt"):
        place = norm_text(place_img.get("alt"))

    title_el = soup.select_one(".heading2_titleName")
    if title_el:
        title = norm_text(title_el.get_text(" ", strip=True))

    race_title_el = soup.select_one(".title16_titleDetail__add2020")
    if race_title_el:
        race_title = norm_text(race_title_el.get_text(" ", strip=True))
        m = re.search(r"(\d+)m", race_title)
        if m:
            distance_m = int(m.group(1))

    return {
        "place_name": place,
        "event_title": title,
        "race_title": race_title,
        "distance_m": distance_m,
    }


def parse_one_race(html: str, hd: str, jcd: str, rno: int, url: str):
    html_main = extract_result_main_html(html)
    soup = BeautifulSoup(html_main, "html.parser")

    result_df = parse_result_table(soup, hd, jcd, rno, url)

    if result_df.empty:
        return None, None, None, "no_result_table"

    start_df = parse_start_table(soup)
    if not start_df.empty:
        result_df = result_df.merge(start_df, on="frame", how="left")
    else:
        result_df["course"] = None
        result_df["st"] = None
        result_df["st_status"] = ""
        result_df["start_move"] = ""

    payout_df = parse_payout_table(soup)
    header = parse_race_header(soup)
    weather = parse_weather(soup)
    kimarite = parse_kimarite(soup)

    trifecta_combo = None
    trifecta_payout_yen = None
    trifecta_popularity = None

    if not payout_df.empty:
        t3 = payout_df[payout_df["bet_type"] == "3連単"]
        if len(t3) > 0:
            trifecta_combo = t3.iloc[0]["combo"]
            trifecta_payout_yen = t3.iloc[0]["payout_yen"]
            trifecta_popularity = t3.iloc[0]["popularity"]

    race_meta = {
        "race_date": hd,
        "jcd": f"{int(jcd):02d}",
        "rno": int(rno),
        "race_id": f"{hd}_{int(jcd):02d}_{int(rno):02d}",
        "url": url,
        **header,
        **weather,
        "kimarite": kimarite,
        "trifecta_combo": trifecta_combo,
        "trifecta_payout_yen": trifecta_payout_yen,
        "trifecta_popularity": trifecta_popularity,
    }

    for k, v in race_meta.items():
        if k not in result_df.columns:
            result_df[k] = v

    return result_df, race_meta, payout_df, None


# =========================================================
# 5. 出走表 parser
# =========================================================

def find_racelist_table(soup: BeautifulSoup):
    candidates = []

    for table in soup.find_all("table"):
        text = table_text(table)

        score = 0
        for key in ["枠", "ボートレーサー", "全国", "当地", "モーター", "ボート", "早見"]:
            if key in text:
                score += 1

        if score >= 5:
            candidates.append((score, len(text), table))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def parse_racer_profile_cell(td):
    text = get_cell_text(td)

    racer_id = None
    racer_name = None
    grade = None
    branch = None
    hometown = None
    age = None
    weight = None

    a = td.find("a", href=re.compile(r"toban=\d+")) if td else None
    if a:
        racer_name = norm_text(a.get_text(" ", strip=True))
        href = a.get("href", "")
        m = re.search(r"toban=(\d{4})", href)
        if m:
            racer_id = m.group(1)

    if racer_id is None:
        m = re.search(r"\b(\d{4})\b", text)
        if m:
            racer_id = m.group(1)

    m = re.search(r"/\s*([AB]\d)", text)
    if m:
        grade = m.group(1)

    if racer_name is None:
        m = re.search(
            r"\b\d{4}\b\s*/\s*[AB]\d\s+(.+?)\s+[\u4e00-\u9fff]{2,4}/[\u4e00-\u9fff]{2,4}",
            text,
        )
        if m:
            racer_name = norm_text(m.group(1))

    m = re.search(r"([\u4e00-\u9fff]{2,4})/([\u4e00-\u9fff]{2,4})", text)
    if m:
        branch = m.group(1)
        hometown = m.group(2)

    m = re.search(r"(\d+)歳\s*/\s*([0-9.]+)kg", text)
    if m:
        age = int(m.group(1))
        weight = float(m.group(2))

    return {
        "racer_id": racer_id,
        "racer_name": racer_name,
        "grade": grade,
        "branch": branch,
        "hometown": hometown,
        "age": age,
        "weight": weight,
        "racer_profile_text": text,
    }


def parse_f_l_avgst_cell(td):
    text = get_cell_text(td)

    f_count = None
    l_count = None
    avg_st = None

    m = re.search(r"F\s*(\d+)", text)
    if m:
        f_count = int(m.group(1))

    m = re.search(r"L\s*(\d+)", text)
    if m:
        l_count = int(m.group(1))

    nums = re.findall(r"\d+\.\d+", text)
    if nums:
        avg_st = float(nums[-1])

    return {
        "f_count": f_count,
        "l_count": l_count,
        "avg_st_entry": avg_st,
        "fl_avgst_text": text,
    }


def parse_three_metric_cell(td, prefix):
    lines = split_lines_from_cell(td)
    nums = [parse_float_safe(x) for x in lines]
    nums = [x for x in nums if x is not None]

    return {
        f"{prefix}_winrate": nums[0] if len(nums) >= 1 else None,
        f"{prefix}_top2_rate": nums[1] if len(nums) >= 2 else None,
        f"{prefix}_top3_rate": nums[2] if len(nums) >= 3 else None,
        f"{prefix}_text": get_cell_text(td),
    }


def parse_no_rate_cell(td, prefix):
    lines = split_lines_from_cell(td)
    nums = [parse_float_safe(x) for x in lines]
    nums = [x for x in nums if x is not None]

    no_val = None
    top2 = None
    top3 = None

    if len(nums) >= 1:
        no_val = int(nums[0]) if float(nums[0]).is_integer() else nums[0]
    if len(nums) >= 2:
        top2 = nums[1]
    if len(nums) >= 3:
        top3 = nums[2]

    return {
        f"{prefix}_no": no_val,
        f"{prefix}_top2_rate": top2,
        f"{prefix}_top3_rate": top3,
        f"{prefix}_text": get_cell_text(td),
    }


def parse_hayami_cell(td):
    text = get_cell_text(td)
    nums = re.findall(r"\d+", text)
    return {
        "hayami": text if text else None,
        "hayami_rno": int(nums[0]) if nums else None,
    }


def parse_series_results_from_tds(tds_after_blank):
    series = []

    for idx, td in enumerate(tds_after_blank, start=1):
        text = get_cell_text(td)
        if text == "":
            continue

        lines = split_lines_from_cell(td)
        nums = re.findall(r"\d+", text)
        floats = re.findall(r"\.\d{2}|F\.?\d{2}|L\.?\d{2}", text)

        series.append({
            "series_cell_index": idx,
            "series_raw": text,
            "series_lines": "|".join(lines),
            "series_first_number": int(nums[0]) if nums else None,
            "series_st_like": floats[0] if floats else None,
        })

    return series


def summarize_series_results(series_list):
    if not series_list:
        return {
            "series_result_count": 0,
            "series_raw_join": None,
        }

    raws = [x["series_raw"] for x in series_list if x.get("series_raw")]
    return {
        "series_result_count": len(series_list),
        "series_raw_join": " / ".join(raws),
    }


def parse_one_racelist(html: str, hd: str, jcd: str, rno: int, url: str):
    html_main = extract_racelist_main_html(html)
    soup = BeautifulSoup(html_main, BS4_PARSER)

    table = find_racelist_table(soup)
    if table is None:
        return None, None, None, "no_racelist_table"

    header = parse_race_header(soup)

    rows = []
    series_rows = []

    tbodies = table.find_all("tbody", recursive=False)

    if tbodies:
        row_groups = []
        for tbody in tbodies:
            trs = tbody.find_all("tr", recursive=False)
            if trs:
                row_groups.append(trs)
    else:
        row_groups = [[tr] for tr in table.find_all("tr")]

    for group in row_groups:
        first_tr = group[0]
        tds = first_tr.find_all("td", recursive=False)

        if len(tds) < 8:
            continue

        frame = parse_int_safe(get_cell_text(tds[0]))
        if frame not in [1, 2, 3, 4, 5, 6]:
            continue

        profile = parse_racer_profile_cell(tds[2])
        flst = parse_f_l_avgst_cell(tds[3])
        national = parse_three_metric_cell(tds[4], "national")
        local = parse_three_metric_cell(tds[5], "local")
        motor = parse_no_rate_cell(tds[6], "motor")
        boat = parse_no_rate_cell(tds[7], "boat")
        hayami = parse_hayami_cell(tds[-1])

        series_tds = []
        if len(tds) > 10:
            series_tds = tds[9:-1]

        series_list = parse_series_results_from_tds(series_tds)
        series_summary = summarize_series_results(series_list)

        base = {
            "race_date": hd,
            "jcd": f"{int(jcd):02d}",
            "rno": int(rno),
            "race_no": int(rno),
            "race_id": f"{hd}_{int(jcd):02d}_{int(rno):02d}",
            "url": url,
            **header,
            "frame": frame,
            "frame_no": frame,
            **profile,
            **flst,
            **national,
            **local,
            **motor,
            **boat,
            **hayami,
            **series_summary,
        }

        rows.append(base)

        for s in series_list:
            sr = {
                "race_date": hd,
                "jcd": f"{int(jcd):02d}",
                "rno": int(rno),
                "race_id": f"{hd}_{int(jcd):02d}_{int(rno):02d}",
                "frame": frame,
                "racer_id": profile.get("racer_id"),
                "racer_name": profile.get("racer_name"),
                **s,
            }
            series_rows.append(sr)

    racelist_df = pd.DataFrame(rows)
    series_df = pd.DataFrame(series_rows)

    race_meta = {
        "race_date": hd,
        "jcd": f"{int(jcd):02d}",
        "rno": int(rno),
        "race_id": f"{hd}_{int(jcd):02d}_{int(rno):02d}",
        "url": url,
        **header,
        "entry_count": len(racelist_df),
    }

    if racelist_df.empty:
        return None, None, None, "empty_entries"

    return racelist_df, race_meta, series_df, None


# =========================================================
# 6. Streamlit app から呼ぶ関数
# =========================================================

def build_racelist_detail(jcd: str, final_hd: str) -> pd.DataFrame:
    all_rows = []
    error_rows = []

    for rno in range(1, 13):
        html, url, fetch_error = fetch_racelist_html(final_hd, jcd, rno)

        if html is None:
            error_rows.append({
                "race_date": final_hd,
                "jcd": f"{int(jcd):02d}",
                "rno": rno,
                "url": url,
                "stage": "fetch",
                "error": fetch_error,
                "html_len": None,
            })
            continue

        try:
            racelist_df, race_meta, series_df, parse_error = parse_one_racelist(
                html=html,
                hd=final_hd,
                jcd=jcd,
                rno=rno,
                url=url,
            )

            if parse_error is not None:
                error_rows.append({
                    "race_date": final_hd,
                    "jcd": f"{int(jcd):02d}",
                    "rno": rno,
                    "url": url,
                    "stage": "parse",
                    "error": parse_error,
                    "html_len": len(html),
                })
                continue

            all_rows.append(racelist_df)

        except Exception as e:
            error_rows.append({
                "race_date": final_hd,
                "jcd": f"{int(jcd):02d}",
                "rno": rno,
                "url": url,
                "stage": "exception",
                "error": repr(e),
                "html_len": len(html),
            })

        time.sleep(SLEEP_SEC + random.random() * 0.05)

    if all_rows:
        out = pd.concat(all_rows, ignore_index=True)
    else:
        out = pd.DataFrame()

    out.attrs["errors_df"] = pd.DataFrame(error_rows)
    return out


def build_results_raw(jcd: str, start_hd: str, prev_hd: str) -> pd.DataFrame:
    all_result_rows = []
    all_meta_rows = []
    all_payout_rows = []
    error_rows = []

    for hd in daterange(start_hd, prev_hd):
        for rno in range(1, 13):
            html, url, fetch_error = fetch_result_html(hd, jcd, rno)

            if html is None:
                error_rows.append({
                    "race_date": hd,
                    "jcd": f"{int(jcd):02d}",
                    "rno": rno,
                    "url": url,
                    "stage": "fetch",
                    "error": fetch_error,
                    "html_len": None,
                })
                continue

            try:
                result_df, race_meta, payout_df, parse_error = parse_one_race(
                    html=html,
                    hd=hd,
                    jcd=jcd,
                    rno=rno,
                    url=url,
                )

                if parse_error is not None:
                    error_rows.append({
                        "race_date": hd,
                        "jcd": f"{int(jcd):02d}",
                        "rno": rno,
                        "url": url,
                        "stage": "parse",
                        "error": parse_error,
                        "html_len": len(html),
                    })
                    continue

                all_result_rows.append(result_df)
                all_meta_rows.append(race_meta)

                if payout_df is not None and not payout_df.empty:
                    all_payout_rows.append(payout_df)

            except Exception as e:
                error_rows.append({
                    "race_date": hd,
                    "jcd": f"{int(jcd):02d}",
                    "rno": rno,
                    "url": url,
                    "stage": "exception",
                    "error": repr(e),
                    "html_len": len(html),
                })

            time.sleep(SLEEP_SEC + random.random() * 0.05)

    if all_result_rows:
        out = pd.concat(all_result_rows, ignore_index=True)
    else:
        out = pd.DataFrame()

    out.attrs["race_meta_df"] = pd.DataFrame(all_meta_rows)
    out.attrs["payout_detail_df"] = (
        pd.concat(all_payout_rows, ignore_index=True)
        if all_payout_rows else pd.DataFrame()
    )
    out.attrs["errors_df"] = pd.DataFrame(error_rows)
    return out


def build_racer_course_style_summary(results_raw: pd.DataFrame) -> pd.DataFrame:
    if results_raw is None or results_raw.empty:
        return pd.DataFrame()

    df = results_raw.copy()

    df["frame"] = pd.to_numeric(df.get("frame"), errors="coerce")
    df["course"] = pd.to_numeric(df.get("course"), errors="coerce")
    df["finish_num"] = pd.to_numeric(df.get("finish_num"), errors="coerce")
    df["rank"] = pd.to_numeric(df.get("rank", df["finish_num"]), errors="coerce")
    df["st"] = pd.to_numeric(df.get("st"), errors="coerce")

    df["racer_id"] = df["racer_id"].astype(str)
    df["racer_name"] = df["racer_name"].astype(str)

    df["is_valid_finish"] = df["finish_num"].notna()
    df["is_win"] = df["finish_num"].eq(1)
    df["is_top2"] = df["finish_num"].isin([1, 2])
    df["is_top3"] = df["finish_num"].isin([1, 2, 3])
    df["is_last"] = df["finish_num"].eq(6)
    df["has_st"] = df["st"].notna()

    df["st_late_020"] = df["st"].gt(0.20)
    df["st_late_025"] = df["st"].gt(0.25)

    df["is_flying"] = df.get("st_status", "").astype(str).eq("F") | df["st"].lt(0)
    df["is_late_start"] = df.get("st_status", "").astype(str).eq("L") | df["st"].gt(1)
    df["is_same_frame_course"] = df["frame"].eq(df["course"])

    df["st_rank_in_race"] = (
        df.groupby("race_id")["st"]
          .rank(method="min", ascending=True)
    )

    df["st_rank_pct_in_race"] = (
        df.groupby("race_id")["st"]
          .rank(method="average", ascending=True, pct=True)
    )

    df["race_avg_st"] = df.groupby("race_id")["st"].transform("mean")
    df["race_min_st"] = df.groupby("race_id")["st"].transform("min")
    df["race_max_st"] = df.groupby("race_id")["st"].transform("max")

    df["st_diff_vs_race_avg"] = df["st"] - df["race_avg_st"]
    df["st_diff_vs_fastest"] = df["st"] - df["race_min_st"]

    df["is_st_rank1"] = df["st_rank_in_race"].eq(1)
    df["is_st_rank2in"] = df["st_rank_in_race"].le(2)
    df["is_st_rank3in"] = df["st_rank_in_race"].le(3)
    df["is_st_last"] = df["st_rank_in_race"].eq(
        df.groupby("race_id")["st_rank_in_race"].transform("max")
    )

    base_cols = ["race_id", "course", "st", "racer_id", "racer_name"]
    tmp = df[base_cols].copy()

    inner = tmp.copy()
    inner["course"] = inner["course"] + 1
    inner = inner.rename(columns={
        "st": "inner_st",
        "racer_id": "inner_racer_id",
        "racer_name": "inner_racer_name",
    })

    outer = tmp.copy()
    outer["course"] = outer["course"] - 1
    outer = outer.rename(columns={
        "st": "outer_st",
        "racer_id": "outer_racer_id",
        "racer_name": "outer_racer_name",
    })

    df = df.merge(
        inner[["race_id", "course", "inner_st", "inner_racer_id", "inner_racer_name"]],
        on=["race_id", "course"],
        how="left",
    )

    df = df.merge(
        outer[["race_id", "course", "outer_st", "outer_racer_id", "outer_racer_name"]],
        on=["race_id", "course"],
        how="left",
    )

    df["st_diff_vs_inner"] = df["st"] - df["inner_st"]
    df["st_diff_vs_outer"] = df["st"] - df["outer_st"]

    df["is_faster_than_inner"] = df["st_diff_vs_inner"].lt(0)
    df["is_faster_than_outer"] = df["st_diff_vs_outer"].lt(0)

    df["is_much_faster_than_inner_003"] = df["st_diff_vs_inner"].le(-0.03)
    df["is_much_faster_than_inner_005"] = df["st_diff_vs_inner"].le(-0.05)

    summary = (
        df.groupby(["racer_id", "racer_name", "course"], dropna=False)
          .agg(
              entries=("race_id", "count"),
              races=("race_id", "nunique"),

              frame_avg=("frame", "mean"),
              frame_mode=("frame", main_value),
              same_frame_course_rate=("is_same_frame_course", "mean"),

              avg_finish=("finish_num", "mean"),
              median_finish=("finish_num", "median"),
              std_finish=("finish_num", "std"),

              win_count=("is_win", "sum"),
              top2_count=("is_top2", "sum"),
              top3_count=("is_top3", "sum"),
              last_count=("is_last", "sum"),

              avg_st=("st", "mean"),
              median_st=("st", "median"),
              std_st=("st", "std"),
              q25_st=("st", q25),
              q75_st=("st", q75),
              min_st=("st", "min"),
              max_st=("st", "max"),

              st_rank_avg=("st_rank_in_race", "mean"),
              st_rank_median=("st_rank_in_race", "median"),
              st_rank1_count=("is_st_rank1", "sum"),
              st_rank2in_count=("is_st_rank2in", "sum"),
              st_rank3in_count=("is_st_rank3in", "sum"),
              st_last_count=("is_st_last", "sum"),

              st_diff_vs_race_avg_avg=("st_diff_vs_race_avg", "mean"),
              st_diff_vs_fastest_avg=("st_diff_vs_fastest", "mean"),

              st_late_020_count=("st_late_020", "sum"),
              st_late_025_count=("st_late_025", "sum"),
              flying_count=("is_flying", "sum"),
              late_start_count=("is_late_start", "sum"),

              faster_than_inner_count=("is_faster_than_inner", "sum"),
              faster_than_outer_count=("is_faster_than_outer", "sum"),
              much_faster_than_inner_003_count=("is_much_faster_than_inner_003", "sum"),
              much_faster_than_inner_005_count=("is_much_faster_than_inner_005", "sum"),

              st_diff_vs_inner_avg=("st_diff_vs_inner", "mean"),
              st_diff_vs_outer_avg=("st_diff_vs_outer", "mean"),
          )
          .reset_index()
    )

    for prefix in ["win", "top2", "top3", "last"]:
        summary[f"{prefix}_rate"] = summary[f"{prefix}_count"] / summary["entries"]

    summary["st_rank1_rate"] = summary["st_rank1_count"] / summary["entries"]
    summary["st_rank2in_rate"] = summary["st_rank2in_count"] / summary["entries"]
    summary["st_rank3in_rate"] = summary["st_rank3in_count"] / summary["entries"]
    summary["st_last_rate"] = summary["st_last_count"] / summary["entries"]

    summary["st_late_020_rate"] = summary["st_late_020_count"] / summary["entries"]
    summary["st_late_025_rate"] = summary["st_late_025_count"] / summary["entries"]
    summary["flying_rate"] = summary["flying_count"] / summary["entries"]
    summary["late_start_rate"] = summary["late_start_count"] / summary["entries"]

    summary["faster_than_inner_rate"] = summary["faster_than_inner_count"] / summary["entries"]
    summary["faster_than_outer_rate"] = summary["faster_than_outer_count"] / summary["entries"]
    summary["much_faster_than_inner_003_rate"] = (
        summary["much_faster_than_inner_003_count"] / summary["entries"]
    )
    summary["much_faster_than_inner_005_rate"] = (
        summary["much_faster_than_inner_005_count"] / summary["entries"]
    )

    summary["st_stability_score"] = (
        1 - (summary["std_st"] / 0.06)
    ).clip(lower=0, upper=1)

    summary["st_speed_score"] = (
        (0.25 - summary["avg_st"]) / (0.25 - 0.12)
    ).clip(lower=0, upper=1)

    summary["st_top_score"] = (
        0.5 * summary["st_rank1_rate"].fillna(0)
        + 0.3 * summary["st_rank2in_rate"].fillna(0)
        + 0.2 * summary["st_rank3in_rate"].fillna(0)
    )

    summary["st_late_risk_score"] = (
        0.7 * summary["st_late_020_rate"].fillna(0)
        + 0.3 * summary["st_late_025_rate"].fillna(0)
    )

    summary["course_result_score"] = (
        0.50 * summary["top3_rate"].fillna(0)
        + 0.30 * summary["top2_rate"].fillna(0)
        + 0.20 * summary["win_rate"].fillna(0)
    )

    summary["attack_score"] = (
        0.35 * summary["st_top_score"].fillna(0)
        + 0.25 * summary["faster_than_inner_rate"].fillna(0)
        + 0.20 * summary["much_faster_than_inner_003_rate"].fillna(0)
        + 0.20 * summary["win_rate"].fillna(0)
    )

    summary["inner_reliability_score"] = np.where(
        summary["course"].eq(1),
        (
            0.45 * summary["win_rate"].fillna(0)
            + 0.25 * summary["top2_rate"].fillna(0)
            + 0.20 * summary["st_stability_score"].fillna(0)
            + 0.10 * (1 - summary["st_late_risk_score"].fillna(0))
        ),
        np.nan,
    )

    summary["outside_pickup_score"] = np.where(
        summary["course"].isin([5, 6]),
        (
            0.60 * summary["top3_rate"].fillna(0)
            + 0.20 * summary["top2_rate"].fillna(0)
            + 0.20 * (1 - summary["last_rate"].fillna(0))
        ),
        np.nan,
    )

    winner_df = df[df["is_win"]].copy()

    if len(winner_df) > 0 and "kimarite" in winner_df.columns:
        kimarite_counts = (
            winner_df
            .groupby(["racer_id", "racer_name", "course", "kimarite"], dropna=False)
            .size()
            .reset_index(name="kimarite_count")
        )

        kimarite_pivot = (
            kimarite_counts
            .pivot_table(
                index=["racer_id", "racer_name", "course"],
                columns="kimarite",
                values="kimarite_count",
                aggfunc="sum",
                fill_value=0,
            )
            .reset_index()
        )

        kimarite_pivot.columns = [
            str(c).replace(" ", "_") for c in kimarite_pivot.columns
        ]

    else:
        kimarite_pivot = pd.DataFrame(
            columns=["racer_id", "racer_name", "course"]
        )

    for col in ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]:
        if col not in kimarite_pivot.columns:
            kimarite_pivot[col] = 0

    kimarite_cols = ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]
    kimarite_pivot["win_kimarite_total"] = kimarite_pivot[kimarite_cols].sum(axis=1)

    for col in kimarite_cols:
        kimarite_pivot[f"{col}_win_rate_in_wins"] = np.where(
            kimarite_pivot["win_kimarite_total"] > 0,
            kimarite_pivot[col] / kimarite_pivot["win_kimarite_total"],
            np.nan,
        )

    if len(kimarite_pivot) > 0:
        kimarite_pivot["main_win_kimarite"] = kimarite_pivot[kimarite_cols].idxmax(axis=1)
    else:
        kimarite_pivot["main_win_kimarite"] = None

    merge_cols = [
        "racer_id", "racer_name", "course",
        "win_kimarite_total",
        "main_win_kimarite",
        "逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ",
        "逃げ_win_rate_in_wins",
        "差し_win_rate_in_wins",
        "まくり_win_rate_in_wins",
        "まくり差し_win_rate_in_wins",
        "抜き_win_rate_in_wins",
        "恵まれ_win_rate_in_wins",
    ]

    summary = summary.merge(
        kimarite_pivot[merge_cols],
        on=["racer_id", "racer_name", "course"],
        how="left",
    )

    summary["course_style_label"] = summary.apply(classify_course_style, axis=1)

    return summary


def classify_course_style(row):
    entries = row.get("entries", 0)
    course = row.get("course", np.nan)

    if pd.isna(course):
        return "コース不明"

    if entries < MIN_ENTRIES_FOR_LABEL:
        return "サンプル少"

    win_rate = row.get("win_rate", 0)
    top2_rate = row.get("top2_rate", 0)
    top3_rate = row.get("top3_rate", 0)
    last_rate = row.get("last_rate", 0)
    st_late_020_rate = row.get("st_late_020_rate", 0)
    attack_score = row.get("attack_score", 0)

    nige_rate = row.get("逃げ_win_rate_in_wins", 0)
    sashi_rate = row.get("差し_win_rate_in_wins", 0)
    makuri_rate = row.get("まくり_win_rate_in_wins", 0)
    mz_rate = row.get("まくり差し_win_rate_in_wins", 0)

    nige_rate = 0 if pd.isna(nige_rate) else nige_rate
    sashi_rate = 0 if pd.isna(sashi_rate) else sashi_rate
    makuri_rate = 0 if pd.isna(makuri_rate) else makuri_rate
    mz_rate = 0 if pd.isna(mz_rate) else mz_rate

    if course == 1:
        if win_rate >= 0.55 and st_late_020_rate <= 0.20:
            return "イン信頼型"
        if win_rate >= 0.40 and top3_rate >= 0.75:
            return "イン堅実型"
        if st_late_020_rate >= 0.35 or win_rate < 0.25:
            return "イン不安型"
        return "イン標準型"

    if course == 2:
        if sashi_rate >= 0.50 and top3_rate >= 0.55:
            return "差し型"
        if makuri_rate >= 0.30 or attack_score >= 0.45:
            return "2コース攻め型"
        if top3_rate >= 0.60 and last_rate <= 0.20:
            return "堅実差し型"
        if st_late_020_rate >= 0.35:
            return "2コース遅れ不安型"
        return "2コース標準型"

    if course in [3, 4]:
        if attack_score >= 0.50 and (makuri_rate + mz_rate) >= 0.35:
            return "センター攻め型"
        if attack_score >= 0.45:
            return "センター先攻型"
        if top3_rate >= 0.60 and last_rate <= 0.20:
            return "展開拾い型"
        if st_late_020_rate >= 0.35 or last_rate >= 0.35:
            return "センター不安型"
        return "センター標準型"

    if course in [5, 6]:
        if top3_rate >= 0.45 and last_rate <= 0.25:
            return "外枠拾い型"
        if attack_score >= 0.45 and (makuri_rate + mz_rate) >= 0.25:
            return "外枠攻め型"
        if last_rate >= 0.45:
            return "外枠苦戦型"
        return "外枠標準型"

    return "標準型"


def add_reliability_flags(summary: pd.DataFrame) -> pd.DataFrame:
    if summary is None or summary.empty:
        return pd.DataFrame()

    out = summary.copy()

    out["sample_level"] = pd.cut(
        out["entries"],
        bins=[-1, 0, 1, 2, 99],
        labels=["none", "low", "mid", "high"],
    )

    out["st_quality"] = "normal"
    out.loc[out["avg_st"] <= 0.12, "st_quality"] = "fast"
    out.loc[out["avg_st"] >= 0.20, "st_quality"] = "slow"

    out["is_sample_small"] = out["entries"] < 3

    return out


def make_debug_empty_reason_df(kind: str, jcd: str, start_hd: str = "", prev_hd: str = "", final_hd: str = ""):
    return pd.DataFrame([{
        "kind": kind,
        "jcd": jcd,
        "start_hd": start_hd,
        "prev_hd": prev_hd,
        "final_hd": final_hd,
        "message": (
            "CSVが空です。公式サイト取得失敗、開催なし、ページ未公開、"
            "またはparserの抽出条件不一致の可能性があります。"
        ),
    }])
