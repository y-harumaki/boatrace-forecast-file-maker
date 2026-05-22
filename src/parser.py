from __future__ import annotations

import re
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

FW_TO_INT = {"１": 1, "２": 2, "３": 3, "４": 4, "５": 5, "６": 6}
RANK_FW_TO_INT = {"１": 1, "２": 2, "３": 3, "４": 4, "５": 5, "６": 6}


def _clean_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    lines = []
    for line in text.splitlines():
        s = re.sub(r"[\t\r\f\v]+", " ", line)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            lines.append(s)
    return lines


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace("%", "")
    if s in {"", "-", "—", " "}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_int(x: Any) -> int | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s in {"", "-", "—", " "}:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _parse_age_weight(s: str) -> tuple[int | None, float | None]:
    m = re.search(r"(\d+)歳\s*/\s*([0-9.]+)kg", s)
    if not m:
        return None, None
    return _to_int(m.group(1)), _to_float(m.group(2))


def _extract_place_event(lines: list[str]) -> tuple[str | None, str | None]:
    # レース場名は画像altで取れない場合があるため、ここではイベント名だけ積極取得
    event_title = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            event_title = line.replace("##", "").strip()
            break
    return None, event_title


def _extract_race_title_distance(lines: list[str]) -> tuple[str | None, int | None]:
    for line in lines:
        m = re.search(r"###\s*(.+?)\s+([0-9]{3,4})m", line)
        if m:
            return m.group(1).strip(), _to_int(m.group(2))
        m = re.search(r"(一般|予選|準優勝戦|優勝戦|特賞|特選|選抜戦|記者選抜|ドリーム戦).*?([0-9]{3,4})m", line)
        if m:
            return m.group(1).strip(), _to_int(m.group(2))
    return None, None


def parse_racelist(html: str, race_date: str, jcd: str, rno: int, url: str) -> pd.DataFrame:
    """BOATRACE racelist ページから1レース6艇分を抽出する。

    公式サイトHTMLのclass名に強依存しないよう、表示テキストの並びから抽出する。
    HTML構造変更時は outputs/debug_html に保存したHTMLを見て調整する。
    """
    lines = _clean_lines(html)
    place_name, event_title = _extract_place_event(lines)
    race_title, distance_m = _extract_race_title_distance(lines)

    # 出走表本文の範囲を切り出す
    start_idx = 0
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if "枠 ボートレーサー" in line:
            start_idx = i
            break
    for i, line in enumerate(lines[start_idx:], start=start_idx):
        if line.startswith("今節成績"):
            end_idx = i
            break
    body = lines[start_idx:end_idx]

    # 枠番ブロックを検出
    frame_positions = []
    for i, line in enumerate(body):
        # web抽出やBS4のget_textでは「１」単独ではなく「１ Image」のように
        # 画像alt等が混ざる場合があるため、行頭の全角艇番だけを見る。
        m_frame = re.match(r"^([１２３４５６])(?:\s|$)", line)
        if m_frame:
            frame = FW_TO_INT[m_frame.group(1)]
            # 直後に「登録番号 / 級別」があるものだけを採用。
            # レース選択ナビ等に出る艇番リンクの誤検出を避ける。
            nxt = " ".join(body[i + 1 : i + 10])
            if re.search(r"\d{4}\s*/\s*[AB]\d", nxt):
                frame_positions.append((i, frame))

    rows: list[dict[str, Any]] = []
    for pos_idx, (pos, frame) in enumerate(frame_positions):
        next_pos = frame_positions[pos_idx + 1][0] if pos_idx + 1 < len(frame_positions) else len(body)
        chunk = body[pos:next_pos]

        profile_idx = None
        racer_id = None
        grade = None
        for j, line in enumerate(chunk):
            m = re.search(r"(\d{4})\s*/\s*([AB]\d)", line)
            if m:
                profile_idx = j
                racer_id = _to_int(m.group(1))
                grade = m.group(2)
                break
        if profile_idx is None:
            continue

        def get_line(offset: int) -> str | None:
            k = profile_idx + offset
            return chunk[k] if 0 <= k < len(chunk) else None

        racer_name = get_line(1)
        branch_hometown = get_line(2) or ""
        branch = None
        hometown = None
        if "/" in branch_hometown:
            parts = branch_hometown.split("/", 1)
            branch, hometown = parts[0].strip(), parts[1].strip()
        age, weight = _parse_age_weight(get_line(3) or "")

        f_count = None
        l_count = None
        avg_st_entry = None
        l_idx = None
        for j in range(profile_idx, min(profile_idx + 12, len(chunk))):
            if re.fullmatch(r"F\d+", chunk[j]):
                f_count = _to_int(chunk[j].replace("F", ""))
            if re.fullmatch(r"L\d+", chunk[j]):
                l_count = _to_int(chunk[j].replace("L", ""))
                l_idx = j

        metric_text = " ".join(chunk[(l_idx + 1 if l_idx is not None else profile_idx + 4) :])
        # 0.15など、先頭ゼロ付き小数も拾う
        nums = re.findall(r"(?<![\d.])\d+\.\d+|(?<![\d.])\d+(?![\d.])", metric_text)
        # BOATRACE表示順: 平均ST, 全国勝率, 全国2連, 全国3連, 当地勝率, 当地2連, 当地3連, モーターNo, モーター2連, モーター3連, ボートNo, ボート2連, ボート3連
        vals = [_to_float(x) for x in nums[:13]] + [None] * max(0, 13 - len(nums))
        avg_st_entry = vals[0]
        national_winrate, national_top2_rate, national_top3_rate = vals[1], vals[2], vals[3]
        local_winrate, local_top2_rate, local_top3_rate = vals[4], vals[5], vals[6]
        motor_no, motor_top2_rate, motor_top3_rate = _to_int(vals[7]), vals[8], vals[9]
        boat_no, boat_top2_rate, boat_top3_rate = _to_int(vals[10]), vals[11], vals[12]

        hayami_matches = re.findall(r"\b(\d{1,2})R\b", " ".join(chunk))
        hayami_rno = _to_int(hayami_matches[-1]) if hayami_matches else None
        hayami = f"{hayami_rno}R" if hayami_rno else None

        # 今節成績らしき数字列。厳密な成績列ではなく、ChatGPTへの補助情報として残す。
        series_raw_join = " / ".join(chunk[(l_idx + 1 if l_idx is not None else profile_idx + 4) :])

        rows.append(
            {
                "race_date": _to_int(race_date),
                "jcd": _to_int(jcd),
                "rno": int(rno),
                "race_id": f"{race_date}_{str(jcd).zfill(2)}_{int(rno):02d}",
                "url": url,
                "place_name": place_name,
                "event_title": event_title,
                "race_title": race_title,
                "distance_m": distance_m,
                "frame": frame,
                "racer_id": racer_id,
                "racer_name": racer_name,
                "grade": grade,
                "branch": branch,
                "hometown": hometown,
                "age": age,
                "weight": weight,
                "racer_profile_text": f"{racer_id} / {grade} {racer_name} {branch}/{hometown} {age}歳/{weight}kg",
                "f_count": f_count,
                "l_count": l_count,
                "avg_st_entry": avg_st_entry,
                "fl_avgst_text": f"F{f_count if f_count is not None else ''} L{l_count if l_count is not None else ''} {avg_st_entry if avg_st_entry is not None else ''}",
                "national_winrate": national_winrate,
                "national_top2_rate": national_top2_rate,
                "national_top3_rate": national_top3_rate,
                "national_text": f"{national_winrate} {national_top2_rate} {national_top3_rate}",
                "local_winrate": local_winrate,
                "local_top2_rate": local_top2_rate,
                "local_top3_rate": local_top3_rate,
                "local_text": f"{local_winrate} {local_top2_rate} {local_top3_rate}",
                "motor_no": motor_no,
                "motor_top2_rate": motor_top2_rate,
                "motor_top3_rate": motor_top3_rate,
                "motor_text": f"{motor_no} {motor_top2_rate} {motor_top3_rate}",
                "boat_no": boat_no,
                "boat_top2_rate": boat_top2_rate,
                "boat_top3_rate": boat_top3_rate,
                "boat_text": f"{boat_no} {boat_top2_rate} {boat_top3_rate}",
                "hayami": hayami,
                "hayami_rno": hayami_rno,
                "series_result_count": None,
                "series_raw_join": series_raw_join,
            }
        )

    return pd.DataFrame(rows)


def _parse_trifecta(text: str) -> tuple[str | None, int | None]:
    m = re.search(r"3連単\s*([1-6]\s*-\s*[1-6]\s*-\s*[1-6])\s*¥?\s*([0-9,]+)", text, re.S)
    if not m:
        return None, None
    return re.sub(r"\s+", "", m.group(1)), _to_int(m.group(2))


def _parse_weather(text: str) -> dict[str, Any]:
    out = {
        "temperature_c": None,
        "weather": None,
        "wind_speed_m": None,
        "wind_direction": None,
        "water_temperature_c": None,
        "wave_height_cm": None,
    }
    m = re.search(r"気温\s*([0-9.]+)℃", text)
    if m:
        out["temperature_c"] = _to_float(m.group(1))
    m = re.search(r"風速\s*([0-9.]+)m", text)
    if m:
        out["wind_speed_m"] = _to_float(m.group(1))
    m = re.search(r"水温\s*([0-9.]+)℃", text)
    if m:
        out["water_temperature_c"] = _to_float(m.group(1))
    m = re.search(r"波高\s*([0-9.]+)cm", text)
    if m:
        out["wave_height_cm"] = _to_float(m.group(1))
    # 天候は水面気象情報周辺に出る単語を緩く取得
    for w in ["晴", "曇り", "雨", "雪", "霧"]:
        if w in text:
            out["weather"] = w
            break
    return out


def parse_raceresult(html: str, race_date: str, jcd: str, rno: int, url: str) -> pd.DataFrame:
    lines = _clean_lines(html)
    text = "\n".join(lines)
    _, event_title = _extract_place_event(lines)
    race_title, distance_m = _extract_race_title_distance(lines)
    trifecta_result, trifecta_payout = _parse_trifecta(text)
    weather = _parse_weather(text)

    decision = None
    m = re.search(r"決まり手\s*\n\s*(逃げ|差し|まくり|まくり差し|抜き|恵まれ)", text)
    if m:
        decision = m.group(1)
    else:
        m = re.search(r"(逃げ|差し|まくり差し|まくり|抜き|恵まれ)", text)
        if m:
            decision = m.group(1)

    # 着順ブロック
    result_rows: list[dict[str, Any]] = []
    in_result = False
    for line in lines:
        if "着 枠 ボートレーサー" in line:
            in_result = True
            continue
        if in_result and line.startswith("スタート情報"):
            break
        if not in_result:
            continue
        m = re.match(r"^([１２３４５６])\s+([1-6])\s+(\d{4})\s+(.+?)(?:\s+[0-9]'[0-9]{2}\"[0-9])?$", line)
        if m:
            result_rows.append(
                {
                    "rank": RANK_FW_TO_INT[m.group(1)],
                    "frame": _to_int(m.group(2)),
                    "racer_id": _to_int(m.group(3)),
                    "racer_name": m.group(4).strip(),
                }
            )

    # スタート情報: 表示順を進入コースとして扱い、表示番号を艇番として扱う
    start_rows: list[dict[str, Any]] = []
    in_start = False
    course_no = 0
    for line in lines:
        if line.startswith("スタート情報"):
            in_start = True
            continue
        if in_start and line.startswith("勝式"):
            break
        if not in_start:
            continue
        # 例: "1 Image .08" / "4 Image .08 まくり" のように
        # 艇番とSTの間に画像altや空白が入るため、艇番の後ろを緩く読む。
        m = re.match(r"^([1-6])\b.*?\.?([0-9]{2})\b\s*(逃げ|差し|まくり差し|まくり|抜き|恵まれ)?", line)
        if m:
            course_no += 1
            start_rows.append(
                {
                    "course": course_no,
                    "frame": _to_int(m.group(1)),
                    "st": _to_float("0." + m.group(2)),
                    "start_decision_text": m.group(3),
                }
            )

    result_df = pd.DataFrame(result_rows)
    start_df = pd.DataFrame(start_rows)
    if result_df.empty:
        return pd.DataFrame()
    if not start_df.empty:
        out = result_df.merge(start_df, on="frame", how="left")
    else:
        out = result_df.copy()
        out["course"] = None
        out["st"] = None
        out["start_decision_text"] = None

    out["race_date"] = _to_int(race_date)
    out["jcd"] = _to_int(jcd)
    out["rno"] = int(rno)
    out["race_id"] = f"{race_date}_{str(jcd).zfill(2)}_{int(rno):02d}"
    out["url"] = url
    out["event_title"] = event_title
    out["race_title"] = race_title
    out["distance_m"] = distance_m
    out["decision"] = decision
    out["trifecta_result"] = trifecta_result
    out["trifecta_payout"] = trifecta_payout
    for k, v in weather.items():
        out[k] = v

    # 列順を安定化
    cols = [
        "race_date", "jcd", "rno", "race_id", "url", "event_title", "race_title", "distance_m",
        "rank", "frame", "racer_id", "racer_name", "course", "st", "decision", "start_decision_text",
        "weather", "wind_speed_m", "wind_direction", "wave_height_cm", "temperature_c", "water_temperature_c",
        "trifecta_result", "trifecta_payout",
    ]
    return out[[c for c in cols if c in out.columns]]
