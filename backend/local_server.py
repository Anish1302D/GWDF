"""Lightweight local HTTP server wrapping `backend.lambda_handler.handler`.

Run from repository root:
    .venv\\Scripts\\python.exe backend/local_server.py --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.lambda_handler import handler  # noqa: E402


class LambdaAdapterHandler(BaseHTTPRequestHandler):
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=False).items() if v}
        event = {
            "rawPath": parsed.path,
            "queryStringParameters": query,
            "requestContext": {"http": {"method": method}},
        }
        resp = handler(event, None)
        body_bytes = (resp.get("body") or "").encode("utf-8")

        self.send_response(int(resp.get("statusCode", 200)))
        for hdr, val in (resp.get("headers") or {}).items():
            self.send_header(hdr, val)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        if method != "HEAD" and body_bytes:
            self.wfile.write(body_bytes)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch("OPTIONS")


def main() -> None:
    parser = argparse.ArgumentParser(description="WellCast Local Lambda API Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--api-dir",
        default=str(REPO_ROOT / "data" / "processed_local" / "api"),
        help="Path to local exported api/ JSON directory",
    )
    args = parser.parse_args()

    os.environ["USE_LOCAL_API"] = "1"
    os.environ["LOCAL_API_DIR"] = args.api_dir
    os.environ.setdefault("ALLOWED_ORIGIN", "*")

    server = ThreadingHTTPServer((args.host, args.port), LambdaAdapterHandler)
    print(f"WellCast local API listening on http://{args.host}:{args.port} (serving {args.api_dir})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
