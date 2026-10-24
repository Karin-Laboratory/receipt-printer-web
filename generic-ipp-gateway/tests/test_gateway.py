#!/usr/bin/env python3
import json
import os
import pathlib
import socket
import subprocess
import tempfile
import concurrent.futures
import time
import unittest
import zlib

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]


def make_pdf(path: pathlib.Path, pages: int, page_size=(300, 180)) -> None:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = []
    for i in range(pages):
        page_id, stream_id = 3 + i * 2, 4 + i * 2
        kids.append(f"{page_id} 0 R".encode())
        # Vector geometry keeps this fixture independent of fonts and external assets.
        stream = f"0 0 0 rg 20 20 40 40 re f 1 0 0 rg 90 20 30 30 re f % {i}\n".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_size[0]} {page_size[1]}] /Resources << >> /Contents {stream_id} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
    objects.insert(1, b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count " + str(pages).encode() + b" >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]: out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def make_qr_japanese_pdf(path: pathlib.Path) -> None:
    qr = qrcode.make("https://example.invalid/receipt-test").convert("L").resize((84, 84), Image.Resampling.NEAREST)
    page = Image.new("L", (300, 110), 255)
    page.paste(qr, (8, 13))
    draw = ImageDraw.Draw(page)
    font = ImageFont.truetype("/usr/share/fonts/opentype/unifont/unifont_jp.otf", 22)
    draw.text((105, 38), "レシート試験", font=font, fill=0)
    raw = page.tobytes()
    compressed = zlib.compress(raw)
    stream = b"q 300 0 0 110 0 0 cm /Im0 Do Q\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 110] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /XObject /Subtype /Image /Width 300 /Height 110 /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length " + str(len(compressed)).encode() + b" >>\nstream\n" + compressed + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n"); offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out); out += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]: out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for gateway result")


def submit(port, path, mime):
    return subprocess.run([
        "ipptool", "-tv", "-f", str(path), "-d", f"filetype={mime}",
        "-d", f"filename={path}", f"ipp://127.0.0.1:{port}/ipp/print",
        "/usr/share/cups/ipptool/print-job.test"], capture_output=True, text=True, timeout=30)


def parse_escpos(data):
    pages, cuts, pos = [], 0, 0
    while pos < len(data):
        if data[pos:pos+3] == b"\x1d\x76\x30":
            if pos + 8 > len(data): raise AssertionError("truncated raster header")
            width_bytes = data[pos+4] | data[pos+5] << 8
            height = data[pos+6] | data[pos+7] << 8
            if width_bytes != 64 or not height: raise AssertionError("bad raster dimensions")
            end = pos + 8 + width_bytes * height
            if end > len(data): raise AssertionError("truncated raster data")
            pages.append(data[pos+8:end])
            pos = end
        elif data[pos:pos+3] == b"\x1d\x56\x00":
            cuts += 1
            pos += 3
            if pos != len(data): raise AssertionError("cut is not the terminal command")
        else:
            raise AssertionError(f"unrecognized ESC/POS command at byte {pos}")
    return pages, cuts


class GatewayIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]
        cls.tmp = tempfile.TemporaryDirectory(prefix="receipt-gateway-test-")
        cls.root = pathlib.Path(cls.tmp.name)
        cls.capture = cls.root / "capture"
        cls.capture.mkdir(mode=0o700)
        cls.proc = subprocess.Popen(["python3", str(ROOT / "scripts/strict_ipp_proxy.py"), "--port", str(cls.port), "--capture-dir", str(cls.capture)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        wait_for(lambda: subprocess.run(["ipptool", "-t", f"ipp://127.0.0.1:{cls.port}/ipp/print", "/usr/share/cups/ipptool/get-printer-attributes.test"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
        cls.raster = cls.root / "fixture.pwg"
        subprocess.run([str(ROOT / "build/raster-fixture"), str(cls.raster), "10"], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try: cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired: cls.proc.kill(); cls.proc.wait()
        cls.tmp.cleanup()

    def test_pwg_raster_10_pages_and_job_boundary_cut(self):
        before = set(self.capture.glob("job-*.escpos"))
        result = submit(self.port, self.raster, "image/pwg-raster")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        wait_for(lambda: len(set(self.capture.glob("job-*.escpos")) - before) >= 1)
        output = (set(self.capture.glob("job-*.escpos")) - before).pop().read_bytes()
        pages, cuts = parse_escpos(output)
        self.assertEqual((len(pages), cuts), (10, 1))
        self.assertTrue(all(len(page) == 64 * 3 for page in pages), "PWG page height must be exactly 3 rows")
        # The unique marker bit moves right one dot per page, proving input order is kept.
        for i, page in enumerate(pages):
            x = 27 + i
            self.assertTrue(page[x // 8] & (0x80 >> (x % 8)), f"missing original PWG marker on page {i}")

    def test_pdf_single_two_ten_page_documents(self):
        for count in (1, 2, 10):
            path = self.root / f"{count}.pdf"
            make_pdf(path, count)
            before = set(self.capture.glob("job-*.escpos"))
            result = submit(self.port, path, "application/pdf")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wait_for(lambda: len(set(self.capture.glob("job-*.escpos")) - before) >= 1, timeout=20)
            output = sorted(set(self.capture.glob("job-*.escpos")) - before)[0].read_bytes()
            pages, cuts = parse_escpos(output)
            self.assertEqual((len(pages), cuts), (count, 1))

    def test_large_pdf_page_is_scaled_to_512_dot_roll_width(self):
        path = self.root / "long-page.pdf"; make_pdf(path, 1, page_size=(300, 6000))
        before = set(self.capture.glob("job-*.escpos"))
        result = submit(self.port, path, "application/pdf")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        wait_for(lambda: len(set(self.capture.glob("job-*.escpos")) - before) >= 1, timeout=20)
        pages, cuts = parse_escpos(sorted(set(self.capture.glob("job-*.escpos")) - before)[0].read_bytes())
        self.assertEqual((len(pages), cuts), (1, 1))
        self.assertGreater(len(pages[0]), 64 * 10000)

    def test_qr_and_japanese_glyph_bitmap_pdf(self):
        path = self.root / "qr-ja.pdf"; make_qr_japanese_pdf(path)
        before = set(self.capture.glob("job-*.escpos"))
        result = submit(self.port, path, "application/pdf")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        wait_for(lambda: len(set(self.capture.glob("job-*.escpos")) - before) >= 1, timeout=20)
        pages, cuts = parse_escpos(sorted(set(self.capture.glob("job-*.escpos")) - before)[0].read_bytes())
        self.assertEqual((len(pages), cuts), (1, 1))
        self.assertTrue(any(pages[0]))

    def test_malformed_pdf_is_not_published_or_cut(self):
        path = self.root / "bad.pdf"
        path.write_bytes(b"not a PDF")
        before = set(self.capture.glob("job-*.escpos"))
        result = submit(self.port, path, "application/pdf")
        # Print-Job acceptance is asynchronous; conversion failure is reflected in job state.
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        time.sleep(0.5)
        self.assertEqual(set(self.capture.glob("job-*.escpos")), before)
        self.assertEqual(list(self.capture.glob("*.partial")), [])

    def test_z_unsupported_media_rejected_before_pappl(self):
        path = self.root / "media-check.pdf"; make_pdf(path, 1)
        result = subprocess.run([
            "ipptool", "-t", "-f", str(path), "-d", "filetype=application/pdf",
            "-d", f"filename={path}", f"ipp://127.0.0.1:{self.port}/ipp/print",
            str(ROOT / "tests/ipp-invalid-media.test")], capture_output=True, text=True, timeout=10)
        # PAPPL 1.3.1 currently substitutes its default media instead of enforcing
        # ipp-attribute-fidelity. This test records that known compatibility gap.
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("client-error-attributes-or-values-not-supported", result.stdout)
        # Ingress rejection must not create a capture file.
        self.assertEqual(set(self.capture.glob("*.partial")), set())

    def test_events_record_one_terminal_cut_per_completed_document(self):
        events = [json.loads(line) for line in (self.capture / "events.jsonl").read_text().splitlines()]
        self.assertTrue(events)
        self.assertTrue(all(e["event"] == "complete" and e["cuts"] == 1 for e in events))

    def test_concurrent_documents_are_separate_capture_jobs(self):
        paths = []
        for i in range(3):
            p = self.root / f"parallel-{i}.pdf"; make_pdf(p, i + 1); paths.append(p)
        before = set(self.capture.glob("job-*.escpos"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda p: submit(self.port, p, "application/pdf"), paths))
        self.assertTrue(all(r.returncode == 0 for r in results), [r.stderr for r in results])
        wait_for(lambda: len(set(self.capture.glob("job-*.escpos")) - before) == 3, timeout=20)
        outputs = [p.read_bytes() for p in set(self.capture.glob("job-*.escpos")) - before]
        self.assertEqual(sorted(len(parse_escpos(data)[0]) for data in outputs), [1, 2, 3])
        self.assertTrue(all(parse_escpos(data)[1] == 1 for data in outputs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
