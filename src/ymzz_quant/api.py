"""Local paper-research HTTP service. It binds to loopback and places no orders."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ymzz_quant.catalog import ROOT
from ymzz_quant.research_config import architecture, default_config, describe_datasets, execute_research
from ymzz_quant.service import polymarket_summary
from ymzz_quant.wallets import add_address, load_book, parse_activity_csv, remove_address, schema

FRONTEND = ROOT / "frontend" / "index.html"
MAX_BODY = 1_000_000


class ResearchHandler(BaseHTTPRequestHandler):
    server_version = "ymzz-research/0.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._bytes(200, FRONTEND.read_bytes(), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/health":
            self._json(200, {"ok": True, "paper_only": True, "deployed": False, "service": "ymzz_quant.api"})
            return
        if parsed.path == "/api/architecture":
            self._json(200, architecture())
            return
        if parsed.path == "/api/datasets":
            self._json(200, describe_datasets())
            return
        if parsed.path == "/api/formulas":
            from ymzz_quant.research_config import FORMULAS

            self._json(200, FORMULAS)
            return
        if parsed.path == "/api/config/default":
            preset = parse_qs(parsed.query).get("preset", ["kraken_btc_spot_assumed_fees"])[0]
            try:
                self._json(200, default_config(preset))
            except KeyError:
                self._json(400, {"ok": False, "errors": [{"field": "preset", "message": "沒有這個預設"}]})
            return
        if parsed.path == "/api/polymarket":
            summary = polymarket_summary(ROOT)
            summary["separate_from_equity"] = True
            summary["shared_bankroll"] = False
            self._json(200, summary)
            return
        if parsed.path == "/api/wallets":
            self._json(200, {"addresses": load_book(ROOT), **schema()})
            return
        self._json(404, {"ok": False, "errors": [{"field": "path", "message": "沒有這個路徑"}]})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._body()
        if body is None:
            return
        if parsed.path == "/api/config/validate":
            from ymzz_quant.research_config import normalize

            _cfg, errors = normalize(body)
            self._json(200 if not errors else 400, {"ok": not errors, "errors": errors})
            return
        if parsed.path == "/api/backtest":
            result = execute_research(body, ROOT)
            self._json(200 if result["ok"] else 400, result)
            return
        if parsed.path == "/api/wallets/add":
            added = add_address(ROOT, body.get("address", ""), body.get("label", ""))
            self._json(200 if added["ok"] else 400, added)
            return
        if parsed.path == "/api/wallets/remove":
            self._json(200, remove_address(ROOT, body.get("address", "")))
            return
        if parsed.path == "/api/wallets/import":
            parsed_csv = parse_activity_csv(body.get("csv", ""))
            self._json(200 if parsed_csv["ok"] else 400, parsed_csv)
            return
        self._json(404, {"ok": False, "errors": [{"field": "path", "message": "沒有這個路徑"}]})

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "errors": [{"field": "body", "message": "JSON 長度不對"}]})
            return None
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "errors": [{"field": "body", "message": "JSON 無法解析"}]})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "errors": [{"field": "body", "message": "需要 JSON 物件"}]})
            return None
        return payload

    def _json(self, code: int, payload: dict) -> None:
        self._bytes(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), ResearchHandler)
    print(f"http://{host}:{port}  paper only, not deployed", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    import sys

    chosen = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    serve(port=chosen)
