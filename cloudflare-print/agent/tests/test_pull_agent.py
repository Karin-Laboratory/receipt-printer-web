import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pull_agent import CaptureAgent, AgentError

JOB = "01234567-89ab-cdef-0123-456789abcdef"
LEASE = "lease-test"


class CaptureOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = CaptureAgent("https://example.invalid", "T" * 40, Path(self.tmp.name) / "spool")
        self.payload = "日本語 receipt test".encode()
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.job = {"id": JOB, "lease_id": LEASE, "digest": self.digest,
                    "bytes": len(self.payload)}

    def tearDown(self):
        self.agent.db.close()
        self.tmp.cleanup()

    def test_claim_and_capture_only(self):
        calls = []
        def mock(method, path, payload=None, lease=None):
            calls.append((method, path))
            if path.endswith("/claim"):
                return (json.dumps({"job": self.job}).encode(), {})
            if path.endswith("/content"):
                return (self.payload, {"x-content-sha256": self.digest})
            if path.endswith("/ack"):
                self.assertEqual(payload["digest"], self.digest)
                return (b'{"ok":true}', {})
            raise ValueError("wrong path")
        self.agent.request = mock
        target = self.agent.poll_once()
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual(target.suffix, ".source")
        self.assertEqual([c[0] for c in calls], ["POST", "GET", "POST"])
        self.assertFalse(list(target.parent.glob("*.partial")))
        self.assertEqual(self.agent.db.execute("SELECT state FROM deliveries").fetchone()[0], "acked")
        with self.assertRaises(AgentError):
            self.agent.capture(self.job)  # Duplicate claim may NEVER replay

    def test_checksum_rejects_corruption_before_any_capture(self):
        self.agent.request = lambda method, path, **kw: (b"tampered", {"x-content-sha256": self.digest})
        with self.assertRaises(AgentError):
            self.agent.capture(self.job)
        self.assertEqual(list(self.agent.destination.glob("*.source")), [])

    def test_ack_loss_marks_uncertain_without_replaying(self):
        def mock(method, path, payload=None, lease=None):
            if path.endswith("/content"):
                return (self.payload, {"x-content-sha256": self.digest})
            raise OSError("ack failed")
        self.agent.request = mock
        with self.assertRaises(OSError):
            self.agent.capture(self.job)
        self.assertEqual(self.agent.db.execute("SELECT state FROM deliveries").fetchone()[0], "uncertain-ack")
        with self.assertRaises(AgentError):
            self.agent.capture(self.job)

    def test_http_loopback_requires_explicit_test_switch(self):
        with self.assertRaises(AgentError):
            CaptureAgent("http://127.0.0.1:8899", "T" * 40, self.agent.destination)
        CaptureAgent("http://127.0.0.1:8899", "T" * 40, self.agent.destination, allow_loopback=True).db.close()


if __name__ == "__main__":
    unittest.main()
