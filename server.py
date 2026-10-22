# -*- coding: utf-8 -*-
"""
로컬 대시보드 서버. 의존성 없이 표준 라이브러리만 사용(Flask 등 설치 불필요).

실행: python server.py  ->  브라우저에서 http://localhost:8765 열기
"""
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import rank_core as rc
import search_volume as sv

if sys.stdout is not None:  # pythonw.exe로 실행되면 콘솔이 없어서 stdout이 None임
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = rc.BASE_DIR
PORT = 8765


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def compute_competitor_analysis():
    path = os.path.join(BASE_DIR, "competitor_snapshot.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 콘솔 조용히

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            fp = os.path.join(BASE_DIR, "dashboard.html")
            with open(fp, encoding="utf-8") as f:
                self._send(200, "text/html; charset=utf-8", f.read().encode("utf-8"))
            return

        if path == "/api/history":
            self._send(200, "application/json", json_bytes(rc.read_history()))
            return

        if path == "/api/keywords":
            self._send(200, "application/json", json_bytes(rc.load_keywords()))
            return

        if path == "/api/search-volume":
            keywords = rc.load_keywords()
            try:
                volumes = sv.get_volumes_cached(keywords)
            except Exception as e:
                self._send(200, "application/json", json_bytes({"configured": True, "error": str(e)}))
                return
            if volumes is None:
                self._send(200, "application/json", json_bytes({"configured": False}))
                return
            self._send(200, "application/json", json_bytes({"configured": True, "volumes": volumes}))
            return

        if path == "/api/competitors":
            data = compute_competitor_analysis()
            self._send(200, "application/json", json_bytes(data or {}))
            return

        if path == "/api/check":
            kw = (qs.get("keyword") or [""])[0].strip()
            if not kw:
                self._send(400, "application/json", json_bytes({"error": "keyword 필요"}))
                return
            try:
                rank, item, total = rc.check_rank(kw)
                rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)
                self._send(200, "application/json", json_bytes({
                    "keyword": kw, "rank": rank, "total": total,
                    "item": item,
                }))
            except Exception as e:
                self._send(500, "application/json", json_bytes({"error": str(e)}))
            return

        if path == "/api/check-all":
            results = []
            for kw in rc.load_keywords():
                try:
                    rank, item, total = rc.check_rank(kw)
                    rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)
                    results.append({"keyword": kw, "rank": rank, "total": total})
                except Exception as e:
                    results.append({"keyword": kw, "error": str(e)})
            self._send(200, "application/json", json_bytes(results))
            return

        self._send(404, "text/plain", b"not found")

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/keywords/add":
            body = self._read_json_body()
            kw = (body.get("keyword") or "").strip()
            if not kw:
                self._send(400, "application/json", json_bytes({"error": "keyword 필요"}))
                return
            keywords = rc.load_keywords()
            if kw not in keywords:
                keywords.append(kw)
                rc.save_keywords(keywords)
            try:
                rank, item, total = rc.check_rank(kw)
                rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)
                self._send(200, "application/json", json_bytes({
                    "keywords": keywords, "rank": rank, "total": total,
                }))
            except Exception as e:
                self._send(200, "application/json", json_bytes({
                    "keywords": keywords, "error": str(e),
                }))
            return

        if path == "/api/keywords/auto-discover":
            existing = rc.load_keywords()
            try:
                discovered = sv.discover_keywords(exclude=existing)
            except Exception as e:
                self._send(200, "application/json", json_bytes({"error": str(e)}))
                return
            if discovered is None:
                self._send(200, "application/json", json_bytes({"configured": False}))
                return

            sv.save_to_cache(discovered)
            keywords = existing + [it["keyword"] for it in discovered]
            rc.save_keywords(keywords)

            checked = []
            for it in discovered:
                kw = it["keyword"]
                try:
                    rank, item, total = rc.check_rank(kw)
                    rc.log_result(kw, rc.DEFAULT_TARGET, rank, item)
                    checked.append({"keyword": kw, "rank": rank, "volume": it["total"]})
                except Exception as e:
                    checked.append({"keyword": kw, "error": str(e), "volume": it["total"]})

            self._send(200, "application/json", json_bytes({"configured": True, "added": checked}))
            return

        if path == "/api/keywords/remove":
            body = self._read_json_body()
            kw = (body.get("keyword") or "").strip()
            keywords = [k for k in rc.load_keywords() if k != kw]
            rc.save_keywords(keywords)
            self._send(200, "application/json", json_bytes({"keywords": keywords}))
            return

        self._send(404, "text/plain", b"not found")


def main():
    no_open = "--no-open" in sys.argv
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    if sys.stdout is not None:  # pythonw.exe로 조용히 실행될 땐 콘솔이 없음
        print(f"대시보드 실행 중: {url}  (Ctrl+C로 종료)")
    if not no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
