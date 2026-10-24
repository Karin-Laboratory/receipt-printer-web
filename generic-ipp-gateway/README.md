# Capture-only 80mm IPP receipt gateway

Offline development prototype for IPP `Print-Job` submission, PDF/PWG Raster conversion, and 512-dot ESC/POS capture. **There is no physical printer transport, raw TCP 9100 sender, USB output, or CT363 deployment.**

## Build and test on Debian 13

```sh
sudo apt-get install build-essential pkg-config libpappl-dev zlib1g-dev poppler-utils cups-ipp-utils python3-pil python3-qrcode fonts-unifont
make
make test
make analyze check-capture-only
```

## Run through the strict IPP admission front end

```sh
install -d -m 700 "$PWD/capture"
python3 scripts/strict_ipp_proxy.py --port 8631 --capture-dir "$PWD/capture"
```

The admission listener is bound to `127.0.0.1:8631`; an internal PAPPL listener uses `127.0.0.1:8632`. Always use the front end. Running `build/gateway` directly bypasses media validation because PAPPL 1.3 substitutes unsupported paper sizes. **Both endpoints are loopback-only, not a security boundary against other processes on the same host**. Do not deploy to shared hosts or expose externally.

Output consists of private `job-N.escpos` captures and `events.jsonl`. Complete documents have a single terminal `GS V 0` cut command. Partial captures are discarded and never automatically replayed.

The front end accepts PDF and **512-dot, monochrome PWG Raster (K/W)** Print-Job submissions. Original PWG rows are decoded into an exact-page-height PDF before PAPPL, avoiding the framework's fixed 200mm page padding. This preserves legitimate white rows, rather than trimming them heuristically. PDF conversion uses Poppler. Explicit A4/58mm or inconsistent media-col dimensions are rejected at IPP ingress. Missing media attributes use the queue's 80mm default. Chunked and Content-Length HTTP requests are supported under a bounded body limit.

**Limitations:** Create-Job/Send-Document are not supported by the strict front end; Windows and Android/Mopria client compatibility has not been tested. No DNS-SD/LAN/TLS/authentication. Maximum ~64MiB per job, 200 pages, and 65535 raster rows/page. Client-originated PWG that is *already* padded to 200mm cannot be unambiguously shortened. Physical feed/cutter settings and printer finish acknowledgments are unknown. Production and physical tests remain NO-GO.

See [Japanese README](README.ja.md), [architecture](docs/architecture.md), [safety](docs/safety.md), [test results](docs/test-results.md), and [license notes](LICENSE-NOTES.md). [Phase 0 Draft PR #1](https://github.com/Karin-Laboratory/receipt-printer-web/pull/1) is separate from implementation Draft PR #2.
