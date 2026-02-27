#!/usr/bin/env python3
"""
Simple HTTP server with Range request support (required for PMTiles).
Usage: python3 server.py [port]
"""
import http.server
import os
import sys


class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        range_header = self.headers.get("Range")
        if not range_header:
            # Add Accept-Ranges to normal responses so browser knows we support it
            super().do_GET()
            return

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            super().do_GET()
            return

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return

        with f:
            file_size = os.fstat(f.fileno()).st_size
            try:
                byte_range = range_header.strip().removeprefix("bytes=")
                start_s, end_s = byte_range.split("-")
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else file_size - 1
            except (ValueError, AttributeError):
                self.send_error(400, "Bad Range header")
                return

            end = min(end, file_size - 1)
            if start < 0 or start > end or start >= file_size:
                self.send_error(416, "Range Not Satisfiable")
                return

            length = end - start + 1
            f.seek(start)
            data = f.read(length)

        self.send_response(206, "Partial Content")
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        # Ensure HEAD responses also advertise Accept-Ranges
        super().do_HEAD()

    def log_message(self, fmt, *args):
        # Suppress noisy access log; uncomment to debug
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    # Serve from project root so /viewer/ and /output/ both work
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with http.server.HTTPServer(("", port), RangeHTTPRequestHandler) as httpd:
        print(f"Serving http://localhost:{port}  (Ctrl-C to stop)")
        httpd.serve_forever()
