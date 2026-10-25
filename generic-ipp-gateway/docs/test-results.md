# Capture-only test evidence

- CI: GitHub Actions `generic-ipp-gateway`; build, GCC `-fanalyzer`, capture-only static guard, Python integration tests.
- Test entry: `make test` runs `unittest discover`. Test service is the strict HTTP/IPP front end bound to `127.0.0.1`, with PAPPL on a second loopback port.
- Media: 80mm allowed/default, explicit A4/58mm refused, `media-col` dimensions checked, invalid HTTP framing and unsupported document formats rejected.
- PDF: 1/2/10-page, 512-dot output, long page, Japanese glyph image and QR embedded.
- PWG: 10-page raster with one terminal cut, exact *source* page height; additional 1/7/19-row cases keep intentional blank rows.
- Safety: simultaneous submission serializes complete jobs, injected capture failure produces no final file/cut/event, malformed PDF produces no final capture.
- ESC/POS verification parses raster-header lengths and skips image payload instead of mistaking raster bytes for cutter commands.
- No test contacted production CT363 or the printer. No Windows/Android hardware test and no guarantee of actual cutting, feed or printing quality.

The first direct reread-of-PWG approach failed because PAPPL streams original PWG input. It was reverted. The current pre-ingress conversion path avoids relying on `papplJobGetFilename` for streaming PWG and is exercised through the proxy.

The number of passes and the final GitHub Actions run must be taken from the current CI run, not assumed from this document. Non-offline Phase 1 remains NO-GO.
