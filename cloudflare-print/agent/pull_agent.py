#!/usr/bin/env python3
"""Outbound-only Cloudflare print-agent: capture source documents, NEVER print."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import urllib.error
import urllib.parse
import urllib.request


class AgentError(RuntimeError):
    pass


def check_dir(folder: Path) -> None:
    if not folder.is_absolute() or folder.is_symlink():
        raise AgentError("capture directory must be an absolute, real directory")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = folder.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise AgentError("capture directory must belong to process user and have mode 0700")


class CaptureAgent:
    def __init__(self, url: str, token: str, destination: Path, *, allow_loopback: bool = False):
        parsed = urllib.parse.urlparse(url)
        loopback = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if parsed.scheme != "https" and not (allow_loopback and loopback):
            raise AgentError("requires HTTPS (except explicit loopback-only test)")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise AgentError("invalid service base URL")
        if not token or len(token) < 32:
            raise AgentError("missing agent credential")
        check_dir(destination)
        self.url = url.rstrip("/")
        self.token = token
        self.destination = destination
        self.db = sqlite3.connect(destination / "agent-state.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL)")
        self.db.commit()

    def request(self, method: str, path: str, *, payload=None, lease=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if lease:
            headers["x-lease-token"] = lease
        data = json.dumps(payload).encode() if payload is not None else (b"" if method == "POST" else None)
        if payload is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        # HTTPS only except test loopback; never proxy through another service.
        with urllib.request.urlopen(request, timeout=20) as res:
            content = res.read(1048577)
            if len(content) > 1048576:
                raise AgentError("response too large")
            return (content, res.headers)

    @staticmethod
    def job_id(value):
        if not isinstance(value, str) or len(value) != 36 or not all(c in "0123456789abcdef-" for c in value):
            raise AgentError("invalid job ID")
        return value

    def capture(self, job):
        jobid = self.job_id(job["id"])
        lease = job["lease_id"]
        digest = job["digest"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise AgentError("invalid job digest")
        if self.db.execute("SELECT 1 FROM deliveries WHERE id=?", (jobid,)).fetchone():
            raise AgentError("duplicate job claim; never replay")
        data, headers = self.request("GET", "/api/agent/jobs/" + jobid + "/content", lease=lease)
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest or headers.get("x-content-sha256") != digest or len(data) != job["bytes"]:
            raise AgentError("content hash/length mismatch; no output")
        partial = self.destination / (jobid + ".partial")
        target = self.destination / (jobid + ".source")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        os.replace(partial, target)
        directory_fd = os.open(self.destination, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        self.db.execute("INSERT INTO deliveries (id,sha256,state,created) VALUES(?,?,?,?)",
                        (jobid, actual, "captured-not-acked", time.time()))
        self.db.commit()
        # At this point the source has been durably captured, but NEVER printed.
        # If ack fails we do not claim/replay the same job automatically.
        try:
            self.request("POST", "/api/agent/jobs/" + jobid + "/ack", payload={"digest": digest}, lease=lease)
        except Exception:
            self.db.execute("UPDATE deliveries SET state=? WHERE id=?", ("uncertain-ack", jobid))
            self.db.commit()
            raise
        self.db.execute("UPDATE deliveries SET state=? WHERE id=?", ("acked", jobid))
        self.db.commit()
        return target

    def poll_once(self):
        data, _ = self.request("POST", "/api/agent/claim")
        job = json.loads(data).get("job")
        if not job:
            return None
        return self.capture(job)


def main():
    parser = argparse.ArgumentParser(description="Capture-only pull agent. No printer output.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--capture-dir", required=True)
    args = parser.parse_args()
    url = os.environ.get("PRINT_CLOUD_URL", "")
    token = os.environ.get("PRINT_AGENT_TOKEN", "")
    agent = CaptureAgent(url, token, Path(args.capture_dir))
    while True:
        try:
            result = agent.poll_once()
            if result:
                print("Source captured (NOT printed): " + result.name, flush=True)
        except (AgentError, OSError, urllib.error.URLError, ValueError, KeyError) as error:
            print("Pull failed, no automatic replay: " + type(error).__name__, flush=True)
        if args.once:
            break
        time.sleep(max(10, args.poll_seconds))


if __name__ == "__main__":
    main()
