"""Local Akış web server with a same-origin proxy to Modal."""

import json
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


MODAL_ENDPOINT = "https://tpberg3tp--akis-workflow-web.modal.run"


class AkisHandler(SimpleHTTPRequestHandler):
    def _proxy(self, method: str) -> None:
        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)

        request = urllib.request.Request(
            MODAL_ENDPOINT + self.path.removeprefix("/api"),
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            response_body = error.read()
            status = error.code
        except Exception as error:
            response_body = json.dumps({"ok": False, "error": str(error)}).encode()
            status = 502

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("GET")
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("POST")
            return
        self.send_error(404)


if __name__ == "__main__":
    print("Akış running at http://127.0.0.1:4173")
    ThreadingHTTPServer(("127.0.0.1", 4173), AkisHandler).serve_forever()
