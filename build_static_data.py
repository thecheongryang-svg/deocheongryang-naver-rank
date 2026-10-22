# -*- coding: utf-8 -*-
"""
GitHub Pages용 정적 데이터(docs/data/*.json) 생성 스크립트.
daily_check.py가 순위기록.csv를 갱신한 뒤, GitHub Actions가 이 스크립트를 실행해서
docs/index.html이 읽는 JSON 파일들을 만든다.
"""
import json
import os

import rank_core as rc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "docs", "data")
os.makedirs(OUT_DIR, exist_ok=True)


def write_json(name, obj):
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def compute_competitor_analysis(data):
    out = {}
    for kw, items in data.items():
        target_idx = None
        for i, it in enumerate(items):
            if rc.DEFAULT_TARGET in it["name"]:
                target_idx = i
                break

        def to_int(v):
            if v is None:
                return 0
            return int(str(v).replace(",", ""))

        rows = []
        for i, it in enumerate(items):
            rows.append({
                "rank": i + 1,
                "name": it["name"],
                "visitorReview": to_int(it["visitorReviewCount"]),
                "blogReview": to_int(it["blogCafeReviewCount"]),
                "imageCount": it.get("imageCount") or 0,
                "distance": it.get("distance") or "",
                "isTarget": i == target_idx,
            })

        above = rows[:target_idx] if target_idx is not None else rows
        avg_review_above = (
            sum(r["visitorReview"] for r in above) / len(above) if above else 0
        )
        out[kw] = {
            "rows": rows,
            "targetRank": (target_idx + 1) if target_idx is not None else None,
            "avgReviewAbove": round(avg_review_above),
        }
    return out


def main():
    write_json("history.json", rc.read_history())
    write_json("keywords.json", rc.load_keywords())

    comp_path = os.path.join(BASE_DIR, "competitor_snapshot.json")
    if os.path.exists(comp_path):
        with open(comp_path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}
    write_json("competitors.json", compute_competitor_analysis(raw))

    print("정적 데이터 생성 완료:", OUT_DIR)


if __name__ == "__main__":
    main()
