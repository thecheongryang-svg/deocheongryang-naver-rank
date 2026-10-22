# -*- coding: utf-8 -*-
"""수동으로 키워드 순위를 바로 확인하고 싶을 때 쓰는 CLI.

사용법: python naver_place_rank.py 키워드1 [키워드2] ...
"""
import sys

import rank_core as rc

sys.stdout.reconfigure(encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print("사용법: python naver_place_rank.py 키워드1 [키워드2] [키워드3] ...")
        print("예시:   python naver_place_rank.py 청량리술집 청량리맛집 청량리이자카야")
        return

    keywords = sys.argv[1:]
    print("=" * 50)
    print(f"네이버 플레이스 순위 체크 ('{rc.DEFAULT_TARGET}' 기준, 광고 제외)")
    print("=" * 50)

    for kw in keywords:
        try:
            rank, item, total = rc.check_rank(kw)
        except Exception as e:
            print(f"[{kw}] 조회 실패: {e}")
            continue

        if rank:
            print(f"[{kw}] {rank}위  (전체 {total}개 중, \"{item['name']}\" / {item['category']})")
        else:
            print(f"[{kw}] 300위 밖 (노출 안 됨)")
        rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)

    print(f"\n기록 저장됨 -> {rc.LOG_PATH}")


if __name__ == "__main__":
    main()
