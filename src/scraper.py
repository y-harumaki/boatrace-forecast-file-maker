from __future__ import annotations

import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.boatrace.jp/owpc/pc/race"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

ALLOWED_PAGE_TYPES = {"racelist", "raceresult", "beforeinfo"}
FINAL_DAY_ALLOWED_PAGE_TYPES = {"racelist"}


@dataclass
class FetchResult:
    url: str
    html: str
    status_code: int


def make_url(page_type: str, rno: int, jcd: str, hd: str) -> str:
    if page_type not in ALLOWED_PAGE_TYPES:
        raise ValueError(f"Unsupported page_type: {page_type}")
    return f"{BASE_URL}/{page_type}?rno={int(rno)}&jcd={str(jcd).zfill(2)}&hd={hd}"


def assert_no_leak(page_type: str, is_final_day: bool) -> None:
    """最終日の未来情報取得を防ぐ。"""
    if is_final_day and page_type not in FINAL_DAY_ALLOWED_PAGE_TYPES:
        raise ValueError(
            "リーク防止: 最終日は racelist のみ取得可能です。"
            f" page_type={page_type} は取得しません。"
        )


def fetch_html(url: str, sleep_sec: float = 0.4, timeout: int = 20) -> FetchResult:
    time.sleep(sleep_sec)
    res = requests.get(url, headers=HEADERS, timeout=timeout)
    res.raise_for_status()
    # BOATRACE公式はShift_JIS系で返る場合があるため apparent_encoding を優先
    res.encoding = res.apparent_encoding or res.encoding
    return FetchResult(url=url, html=res.text, status_code=res.status_code)
