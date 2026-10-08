"""Read-only bridge to an existing glab login; credentials stay with glab."""

import subprocess
import threading
from urllib.parse import urlsplit

from .model import ScopeError, require


class GlabTransport:
    def __init__(self, endpoint, executable="glab"):
        parsed = urlsplit(endpoint)
        require(parsed.scheme == "https" and parsed.path == "/api/v4" and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment, "glab requires an HTTPS /api/v4 endpoint")
        self.endpoint, self.host, self.executable = endpoint, parsed.netloc, executable

    def request(self, method, url, headers, body, timeout):
        from .collect import MAX_RESPONSE
        require(method == "GET" and body is None and url.startswith(self.endpoint + "/"),
                "glab bridge permits same-endpoint GET only")
        endpoint = url[len(self.endpoint) + 1:]
        args = [self.executable, "api", endpoint, "--hostname", self.host, "--method", "GET", "--include"]
        if "If-None-Match" in headers:
            args += ["--header", "If-None-Match: " + headers["If-None-Match"]]
        chunks = []
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise ScopeError("GLAB_UNAVAILABLE") from exc

        def read():
            data = process.stdout.read(MAX_RESPONSE + 65537)
            chunks.append(data)
            if len(data) > MAX_RESPONSE + 65536:
                process.kill()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill(); process.wait(); reader.join(timeout=1)
            raise ScopeError("GLAB_TIME_CAP") from exc
        reader.join(timeout=1)
        require(not reader.is_alive(), "GLAB_RESPONSE_UNAVAILABLE")
        raw = b"".join(chunks)
        require(len(raw) <= MAX_RESPONSE + 65536, "RESPONSE_BYTE_CAP")
        raw = raw.replace(b"\r\n", b"\n")
        head, separator, payload = raw.partition(b"\n\n")
        require(separator and head.startswith(b"HTTP/"), "GLAB_AUTH_OR_RESPONSE_UNAVAILABLE")
        lines = head.decode("ascii").splitlines()
        try:
            code = int(lines[0].split()[1])
            response_headers = {k.strip().lower(): v.strip() for k, v in
                                (line.split(":", 1) for line in lines[1:] if ":" in line)}
        except (ValueError, IndexError) as exc:
            raise ScopeError("GLAB_RESPONSE_UNAVAILABLE") from exc
        require(len(payload) <= MAX_RESPONSE, "RESPONSE_BYTE_CAP")
        return code, response_headers, payload
