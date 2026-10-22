# -*- coding: utf-8 -*-
"""
매일 자동으로 돌아가는 체크 스크립트. 인자 없이 keywords.txt에 적힌 키워드를 전부 조회해서
순위기록.csv에 쌓는다. Windows 작업 스케줄러가 매일 이 스크립트를 실행한다.
"""
import os
import sys
from datetime import datetime

import rank_core as rc

sys.stdout.reconfigure(encoding="utf-8")

LOG_FILE = os.path.join(rc.BASE_DIR, "daily_run.log")


def log_line(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    keywords = rc.load_keywords()
    if not keywords:
        log_line("keywords.txt에 키워드가 없음 - 종료")
        return

    log_line(f"일일 순위 체크 시작 ({len(keywords)}개 키워드)")
    for kw in keywords:
        try:
            rank, item, total = rc.check_rank(kw)
            rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)
            rank_text = f"{rank}위" if rank else "300위 밖"
            log_line(f"  {kw}: {rank_text}")
        except Exception as e:
            log_line(f"  {kw}: 실패 - {e}")
    log_line("완료")


if __name__ == "__main__":
    main()
