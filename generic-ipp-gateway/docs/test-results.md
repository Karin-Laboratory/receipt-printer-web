# Test results

Tested on Debian 13 development host, 2026-10-24. PAPPL 1.3.1, libcups 2.4.10, Poppler 25.03.0, GCC 14.2. The service binds only to `127.0.0.1` during tests.

`make test` runs 9 tests:

- PDF with 1, 2, and 10 pages; one terminal cut per job.
- 10-page PWG Raster; 512-dot ESC/POS raster blocks and a single terminal cut.
- Long PDF page; output width stays 512 dots.
- QR image and Japanese glyph bitmap embedded in PDF.
- Three simultaneous PDF submissions; separate capture files and no interleaved page counts.
- Malformed PDF; no completed capture file.
- Capture failure after a partial write; no completed file, event, or automatic replay.
- IPP Get-Printer-Attributes and Print-Job.
- Unsupported A4 media behavior: records PAPPL 1.3.1's substitution response as a known gap rather than asserting rejection.

The ESC/POS verifier parses `GS v 0` command headers and skips the declared raster payload before looking for the terminal `GS V 0`. It does not search for `1D 56` byte pairs inside arbitrary image data. The PWG path uses a fixed media-length header in PAPPL and may produce blank rows after each source page; its test does not imply variable-length receipt-quality output.

Windows, Android, live LAN ingress, Avahi discovery, physical printer protocol, paper feed, cut position, and hardware status queries were not tested. No test opened a physical printer connection.
