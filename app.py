"""Small web interface for printing text on an ESC/POS network printer."""

import os
import socket

from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

MAX_TEXT_LENGTH = 4_000


def printer_address() -> tuple[str, int]:
    host = os.environ.get("RECEIPT_PRINTER_HOST", "192.0.2.20").strip()
    try:
        port = int(os.environ.get("RECEIPT_PRINTER_PORT", "9100"))
    except ValueError as exc:
        raise ValueError("RECEIPT_PRINTER_PORT must be an integer") from exc
    if not host or not 1 <= port <= 65535:
        raise ValueError("invalid printer address")
    return host, port


def print_receipt(text: str) -> None:
    """Send plain UTF-8 text and a cut command over raw TCP."""
    host, port = printer_address()
    payload = b"\x1b@" + text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    payload += b"\n\n\n\x1dV\x00"
    with socket.create_connection((host, port), timeout=5) as printer:
        printer.sendall(payload)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.post("/print")
def print_text():
    text = request.form.get("text", "")
    if not text.strip():
        return jsonify(error="Enter some text before printing."), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify(error=f"Text is limited to {MAX_TEXT_LENGTH} characters."), 400
    try:
        print_receipt(text)
    except (OSError, ValueError) as exc:
        app.logger.exception("printer request failed")
        return jsonify(error=f"Could not print: {exc}"), 502
    return jsonify(status="printed")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=False)
