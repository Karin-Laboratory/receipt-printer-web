#!/usr/bin/env python3
import os
import pathlib
import socket
import subprocess
import tempfile
import time
import unittest

from test_gateway import make_pdf, submit, wait_for

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FailureInjection(unittest.TestCase):
    def test_partial_capture_is_discarded_and_not_retried_or_cut(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="receipt-gateway-failure-") as td:
            root = pathlib.Path(td)
            capture = root / "capture"; capture.mkdir(mode=0o700)
            pdf = root / "job.pdf"; make_pdf(pdf, 2)
            env = os.environ.copy(); env["GW_TEST_FAIL_AFTER_BYTES"] = "20"
            proc = subprocess.Popen([str(ROOT / "build/gateway-test"), "--port", str(port), "--capture-dir", str(capture)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_for(lambda: subprocess.run(["ipptool", "-t", f"ipp://127.0.0.1:{port}/ipp/print", "/usr/share/cups/ipptool/get-printer-attributes.test"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
                result = submit(port, pdf, "application/pdf")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                time.sleep(0.5)
                self.assertEqual(list(capture.glob("job-*.escpos")), [])
                self.assertEqual(list(capture.glob("*.partial")), [])
                self.assertFalse((capture / "events.jsonl").exists())
            finally:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()


if __name__ == "__main__":
    unittest.main(verbosity=2)
