# -*- coding: utf-8 -*-
"""
네이버 플레이스 순위 조회 공통 로직. naver_place_rank.py(수동 CLI), daily_check.py(매일
자동 실행), server.py(대시보드)가 전부 이 모듈을 가져다 쓴다.
"""
import csv
import os
import time
from datetime import datetime

import requests

API_URL = "https://api.place.naver.com/graphql"
HEADERS = {
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "referer": "https://m.place.naver.com/",
}

QUERY = """
query getPlaces($input: PlaceListInput) {
  placeList(input: $input) {
    businesses {
      total
      items {
        id
        name
        category
        roadAddress
        visitorReviewCount
        blogCafeReviewCount
        imageCount
        distance
      }
    }
  }
}
"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_X = "127.0418181"
DEFAULT_Y = "37.5777750"
DEFAULT_TARGET = "더청량"
LOG_PATH = os.path.join(BASE_DIR, "순위기록.csv")
KEYWORDS_PATH = os.path.join(BASE_DIR, "keywords.txt")
PAGE_SIZE = 60
MAX_RANK = 300


def load_keywords():
    if not os.path.exists(KEYWORDS_PATH):
        return []
    with open(KEYWORDS_PATH, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_keywords(keywords):
    # 중복 제거, 순서 유지, 빈 값 제거
    seen = set()
    clean = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            clean.append(kw)
    with open(KEYWORDS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(clean) + ("\n" if clean else ""))
    return clean


def fetch_page(keyword, start, display, x=DEFAULT_X, y=DEFAULT_Y):
    payload = {
        "operationName": "getPlaces",
        "query": QUERY,
        "variables": {
            "input": {
                "query": keyword,
                "start": start,
                "display": display,
                "deviceType": "mobile",
                "isNx": False,
                "businessType": "place",
                "x": x,
                "y": y,
            }
        },
    }
    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"네이버 API 오류: {data['errors']}")
    biz = data["data"]["placeList"]["businesses"]
    return biz["items"], biz["total"]


def check_rank(keyword, target_name=DEFAULT_TARGET, x=DEFAULT_X, y=DEFAULT_Y, max_rank=MAX_RANK):
    """target_name이 포함된 업체를 찾을 때까지 페이지를 넘기며 순위를 센다."""
    start = 1
    while start <= max_rank:
        display = min(PAGE_SIZE, max_rank - start + 1)
        items, total = fetch_page(keyword, start, display, x, y)
        if not items:
            break
        for i, item in enumerate(items):
            if target_name in item["name"]:
                return start + i, item, total
        start += display
        if start > total:
            break
        time.sleep(0.25)
    return None, None, None


def log_result(keyword, target_name, rank, item):
    is_new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["조회일시", "키워드", "찾는업체", "순위", "실제상호", "카테고리", "주소"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            keyword,
            target_name,
            rank if rank else "",
            item["name"] if item else "",
            item["category"] if item else "",
            item["roadAddress"] if item else "",
        ])


def read_history():
    """CSV 전체를 리스트[dict]로 읽어온다."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
