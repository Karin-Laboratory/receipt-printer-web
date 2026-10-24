#!/usr/bin/env python3
"""Capture-only IPP admission gateway; no printer output or configurable network.

Public loopback 8631 -> private loopback PAPPL 8632. Reject non-80mm
attributes BEFORE PAPPL can substitute them. PWG is converted to exact-size
PDF (same one-job semantics) to avoid PAPPL's fixed-height PWG streaming path.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from media_guard import IPPFormatError, parse_ipp, admit_job_media

MAX_BODY = 64 * 1024 * 1024 + 65536
FORWARD = {0x0008, 0x0009, 0x000a, 0x000b, 0x0012, 0x0016}
WRITE = {0x0002, 0x0004}
MIME_PWG = b"image/pwg-raster"
MIME_PDF = b"application/pdf"


def error_response(request: bytes, status: int):
    version = request[:2] if len(request) >= 2 and request[0] in (1, 2) else b"\x02\x00"
    request_id = request[4:8] if len(request) >= 8 else b"\0\0\0\1"

    def item(tag, name, value):
        name, value = name.encode("ascii"), value.encode("ascii")
        return bytes([tag]) + len(name).to_bytes(2, "big") + name + len(value).to_bytes(2, "big") + value

    return (version + status.to_bytes(2, "big") + request_id + b"\x01" +
            item(0x47, "attributes-charset", "utf-8") +
            item(0x48, "attributes-natural-language", "en") + b"\x03")


def convert_document(body: bytes, offset: int, attrs, executable: Path):
    fmts = [a.data for a in attrs if a.group == 1 and a.name == "document-format"]
    if len(fmts) != 1:
        raise IPPFormatError("missing or ambiguous document-format")
    if fmts[0] == MIME_PDF:
        return body
    if fmts[0] != MIME_PWG:
        raise IPPFormatError("unsupported document-format")
    # This also prevents clients from supplying odd repeated-name forms whose
    # original wire representation we could not rewrite unambiguously.
    name = b"document-format"
    needle = b"\x49" + len(name).to_bytes(2, "big") + name + len(MIME_PWG).to_bytes(2, "big") + MIME_PWG
    replacement = b"\x49" + len(name).to_bytes(2, "big") + name + len(MIME_PDF).to_bytes(2, "big") + MIME_PDF
    if body[:offset].count(needle) != 1:
        raise IPPFormatError("noncanonical PWG format attribute")
    with tempfile.TemporaryDirectory(prefix="ipp-pwg-offline-") as td:
        raw, pdf = Path(td) / "input.pwg", Path(td) / "output.pdf"
        raw.write_bytes(body[offset:])
        result = subprocess.run([str(executable), str(raw), str(pdf)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=60, check=False)
        if result.returncode or not pdf.is_file() or pdf.stat().st_size > MAX_BODY:
            raise IPPFormatError("PWG conversion failed")
        return body[:offset].replace(needle, replacement, 1) + pdf.read_bytes()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ReceiptCaptureIPP/0.2"

    def log_message(self, _fmt, *_args):
        return  # Do not expose document titles, IPP attributes, or private data.

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self):
        if self.path != "/ipp/print" or self.headers.get_content_type() != "application/ipp":
            self.respond(404, b"", "text/plain")
            return
        self.connection.settimeout(70)
        try:
            encoding = self.headers.get("Transfer-Encoding", "").strip().lower()
            if encoding:
                if encoding != "chunked" or "Content-Length" in self.headers:
                    raise ValueError("ambiguous HTTP framing")
                chunks, total = [], 0
                while True:
                    header = self.rfile.readline(96)
                    if not header.endswith(b"\r\n") or not header:
                        raise ValueError("bad chunk framing")
                    # Reject extensions to prevent request-smuggling ambiguity.
                    sizeword = header[:-2]
                    if not sizeword or any(v not in b"0123456789abcdefABCDEF" for v in sizeword):
                        raise ValueError("bad chunk size")
                    size = int(sizeword, 16)
                    if size > MAX_BODY - total:
                        raise ValueError("IPP document too large")
                    if size == 0:
                        if self.rfile.read(2) != b"\r\n":
                            raise ValueError("unsupported HTTP trailers")
                        break
                    part = self.rfile.read(size)
                    if len(part) != size or self.rfile.read(2) != b"\r\n":
                        raise ValueError("short HTTP chunk")
                    chunks.append(part)
                    total += size
                data = b"".join(chunks)
            else:
                length = int(self.headers.get("Content-Length", "0"))
                if not (8 <= length <= MAX_BODY):
                    raise ValueError("invalid document length")
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("short HTTP body")
            if len(data) < 8:
                raise ValueError("truncated IPP header")
        except (ValueError, OSError):
            self.respond(400, b"", "text/plain")
            return
        try:
            operation, attrs, offset = parse_ipp(data)
            if operation in WRITE:
                if not admit_job_media(attrs):
                    self.respond(200, error_response(data, 0x040b), "application/ipp")
                    return
                if operation == 0x0002:
                    data = convert_document(data, offset, attrs, self.server.converter)
            elif operation not in FORWARD:
                # Unsupported Create-Job/Send-Document and attribute changes
                # fail closed rather than bypass strict media admission.
                self.respond(200, error_response(data, 0x0501), "application/ipp")
                return
        except (IPPFormatError, OSError, subprocess.SubprocessError):
            self.respond(200, error_response(data, 0x040b), "application/ipp")
            return
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.server.backend_port, timeout=60)
            conn.request("POST", self.path, body=data,
                         headers={"Content-Type": "application/ipp", "Connection": "close"})
            response = conn.getresponse()
            result = response.read(MAX_BODY + 1)
            if len(result) > MAX_BODY:
                raise OSError("oversized IPP response")
            self.respond(response.status, result, response.getheader("Content-Type", "application/ipp"))
            conn.close()
        except (OSError, http.client.HTTPException):
            self.respond(503, b"", "text/plain")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8631)
    p.add_argument("--capture-dir", required=True)
    p.add_argument("--testing", action="store_true", help="Use test-only fault injection binary")
    args = p.parse_args()
    if not (1024 <= args.port <= 65533):
        p.error("invalid port")
    root = Path(__file__).resolve().parents[1]
    binary = root / "build" / ("gateway-test" if args.testing else "gateway")
    converter = root / "build" / "pwg2pdf"
    if not binary.is_file() or not converter.is_file():
        p.error("build gateway and pwg2pdf first")
    # No external binding or printer transport, even via configuration.
    backend_port = args.port + 1
    proc = subprocess.Popen([str(binary), "--port", str(backend_port),
                             "--capture-dir", args.capture_dir],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
            server.backend_port = backend_port
            server.converter = converter
            server.serve_forever(poll_interval=.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
