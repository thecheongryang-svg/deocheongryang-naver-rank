# -*- coding: utf-8 -*-
"""
네이버 검색광고 API(공식)로 키워드의 월간 검색량(PC+모바일)을 가져온다.

이건 지금까지 쓰던 "네이버 플레이스 순위" API와는 완전히 다른, 네이버가 공식으로 제공하는
API라서 전용 인증키가 필요하다 - searchad_config.json에 발급받은 키를 넣어야 작동한다.

키 발급 방법:
1. https://searchad.naver.com 접속해서 네이버 검색광고 계정으로 로그인 (없으면 가입 - 사업자 인증 필요)
2. 우측 상단 도구 > API 사용 관리
3. "API 사용 신청" 후 발급되는 3가지 값을 searchad_config.json에 채워 넣기:
   - ACCESS LICENSE -> api_key
   - SECRET KEY -> secret_key   (발급 시 한 번만 보여줌 - 꼭 복사해두기)
   - 고객ID(CUSTOMER ID) -> customer_id  (화면 우측 상단에 표시된 숫자)

참고: 네이버는 keywordstool 데이터를 "검색광고 상품의 구매/집행/관리 목적"으로 쓰라고
안내하고 있다. 우리 가게가 실제로 어떤 키워드로 광고/마케팅을 할지 판단하는 용도로 쓰는 거라
이 범위 안에 있지만, 참고로 적어둔다.
"""
import base64
import hashlib
import hmac
import json
import os
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "searchad_config.json")
CACHE_PATH = os.path.join(BASE_DIR, "search_volume_cache.json")
API_BASE = "https://api.naver.com"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if not all(cfg.get(k) for k in ("api_key", "secret_key", "customer_id")):
        return None
    return cfg


def _signature(secret_key, timestamp, method, uri):
    sign = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode(), sign.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers(cfg, method, uri):
    timestamp = str(round(time.time() * 1000))
    return {
        "X-API-KEY": cfg["api_key"],
        "X-CUSTOMER": cfg["customer_id"],
        "X-Timestamp": timestamp,
        "X-Signature": _signature(cfg["secret_key"], timestamp, method, uri),
    }


def _to_int(v):
    # "< 10" 처럼 소량일 때 문자열로 오는 경우가 있어서 숫자만 추출
    s = str(v).replace(",", "").strip()
    digits = "".join(c for c in s if c.isdigit())
    return int(digits) if digits else 0


def _raw_keywordstool(hint_keywords):
    """keywordstool API를 그대로 호출해서 전체 결과를 돌려준다.

    네이버 키워드도구는 넣은 키워드 자체뿐 아니라, 그 키워드에서 파생되는 '연관키워드'를
    수십~수백 개 같이 돌려준다 (이게 바로 자동 키워드 발굴에 쓰는 부분).
    반환: [{keyword, pc, mobile, total}, ...] (relKeyword 원본 그대로, 중복 없음)
    """
    cfg = load_config()
    if not cfg:
        return None

    uri = "/keywordstool"
    hint = ",".join(kw.replace(" ", "") for kw in hint_keywords)
    headers = _headers(cfg, "GET", uri)
    resp = requests.get(
        API_BASE + uri, headers=headers,
        params={"hintKeywords": hint, "showDetail": "1"}, timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "keywordList" not in data:
        raise RuntimeError(f"검색광고 API 오류: {data}")

    items = []
    for item in data["keywordList"]:
        pc = _to_int(item.get("monthlyPcQcCnt", 0))
        mobile = _to_int(item.get("monthlyMobileQcCnt", 0))
        items.append({"keyword": item["relKeyword"], "pc": pc, "mobile": mobile, "total": pc + mobile})
    return items


def fetch_volumes(keywords):
    """keywords(list[str])에 대한 {키워드: {pc, mobile, total}} 딕셔너리를 돌려준다.

    네이버는 공백을 없앤 키워드만 받기 때문에 "청량리 술집" 같은 건 "청량리술집"으로 변환해서
    조회하되, 결과는 원래 키워드 기준으로 매핑해서 돌려준다.
    """
    items = _raw_keywordstool(keywords)
    if items is None:
        return None  # 키 미설정 - 호출한 쪽에서 안내 처리

    by_norm = {it["keyword"].replace(" ", ""): it for it in items}
    result = {}
    for kw in keywords:
        norm = kw.replace(" ", "")
        hit = by_norm.get(norm)
        result[kw] = {"pc": hit["pc"], "mobile": hit["mobile"], "total": hit["total"]} if hit else \
            {"pc": 0, "mobile": 0, "total": 0}
    return result


# 자동 키워드 발굴에 쓰는 기본 씨앗 키워드 - 위치 기반으로 넣으면 네이버가 알아서
# "청량리술집", "청량리역맛집", "청량리포장마차" 류의 지역+업종 조합을 연관키워드로 던져준다.
DEFAULT_SEEDS = ["청량리", "청량리역"]

# 발굴된 연관키워드 중 우리 가게랑 상관없는 것(부동산, 맛집 체인 등)까지 다 등록되는 걸
# 막기 위한 관련성 필터 - 이 중 하나라도 포함해야 등록 후보로 인정
RELEVANCE_TERMS = ["청량리", "제기동", "회기", "전농동", "청량리역"]
CATEGORY_TERMS = ["술집", "이자카야", "포차", "요리주점", "선술집", "바", "펍", "야장", "맥주", "호프", "와인", "다이닝"]


def discover_keywords(seeds=None, min_volume=10, limit=20, exclude=None):
    """대표키워드(seeds)에서 연관키워드를 뽑아서, 실제 검색량 있고 관련성 있는 것만 골라낸다.

    exclude: 이미 추적 중인 키워드 목록 (중복 등록 방지용)
    반환: [{keyword, pc, mobile, total}, ...] 검색량 내림차순, 최대 limit개. 키 미설정이면 None.
    """
    seeds = seeds or DEFAULT_SEEDS
    exclude_norm = {k.replace(" ", "") for k in (exclude or [])}

    items = _raw_keywordstool(seeds)
    if items is None:
        return None

    picked = []
    seen = set()
    for it in items:
        kw, norm = it["keyword"], it["keyword"].replace(" ", "")
        if norm in seen or norm in exclude_norm:
            continue
        if it["total"] < min_volume:
            continue
        is_local = any(t in kw for t in RELEVANCE_TERMS)
        is_category = any(t in kw for t in CATEGORY_TERMS)
        if not (is_local and is_category):
            # "청량리" 단독처럼 업종 정보가 없거나, 업종 단어만 있고 지역이 없는 키워드는 제외 -
            # 지역+업종이 같이 들어간 조합만 우리 가게와 관련 있다고 본다
            continue
        seen.add(norm)
        picked.append(it)

    picked.sort(key=lambda x: -x["total"])
    return picked[:limit]


def save_to_cache(items):
    """discover_keywords 등에서 이미 받아온 검색량을 캐시에 바로 써넣는다 (재조회 안 해도 되게)."""
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    now = time.time()
    for it in items:
        cache[it["keyword"]] = {"pc": it["pc"], "mobile": it["mobile"], "total": it["total"], "_fetched_at": now}
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_volumes_cached(keywords, max_age_days=7):
    """캐시가 있고 7일 이내면 그걸 쓰고, 없거나 오래됐으면 새로 조회해서 캐시에 저장.
    검색량은 하루 단위로 거의 안 바뀌고, API 호출 한도를 아끼기 위함."""
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    now = time.time()
    stale_or_missing = [
        kw for kw in keywords
        if kw not in cache or (now - cache[kw].get("_fetched_at", 0)) > max_age_days * 86400
    ]
    if stale_or_missing:
        fresh = fetch_volumes(stale_or_missing)
        if fresh is None:
            return None
        for kw, v in fresh.items():
            v["_fetched_at"] = now
            cache[kw] = v
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    return {kw: cache.get(kw, {"pc": 0, "mobile": 0, "total": 0}) for kw in keywords}
