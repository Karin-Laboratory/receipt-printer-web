# Capture-only 80 mm IPP receipt gateway

This is an isolated prototype for accepting IPP print jobs and converting them to 512-dot ESC/POS byte streams. It is deliberately capture-only: it has no printer address setting, RAW TCP/9100 transport, USB/serial transport, or usable device-write callback. Successful jobs are saved as local `.escpos` files. **Building or running this program cannot print to a physical printer.**

The project uses PAPPL 1.3.x, libcups raster support, and Poppler's `pdftoppm`. The IPP listener binds to `127.0.0.1` by default. The printer queue is `80mm-capture`; the test endpoint is `/ipp/print`.

## Build and test on Debian 13

Install development and test dependencies:

```sh
sudo apt-get install build-essential pkg-config libpappl-dev poppler-utils cups-ipp-utils python3-pil python3-qrcode fonts-unifont
make
make test
make analyze
make check-capture-only
```

Start a local capture-only IPP service:

```sh
install -d -m 700 "$PWD/capture"
./build/gateway --port 8631 --capture-dir "$PWD/capture"
```

Use an absolute capture path owned by the current user with mode `0700`. The default listener is loopback, so Windows and Android devices cannot connect to it. A later deployment phase must explicitly design LAN ingress, firewalling, authentication, service discovery, and TLS before changing that boundary.

Each completed job becomes `job-N.escpos`; `events.jsonl` records job ID, page count, final-cut count, and byte count. Files are mode `0600`. Failed jobs do not publish an `.escpos` file. A `.partial` file is never replayed automatically.

## Current support

- PDF is rasterized using `/usr/bin/pdftoppm`, scaled to 512 dots, and rendered as 180 dpi monochrome data.
- PAPPL's built-in PWG Raster path is accepted and captured at 512 output dots. PAPPL 1.3 uses its fixed 200 mm media length for this streaming path, so it may pad each source page with blank rows. Variable page length for PWG Raster is not complete.
- Page callbacks never emit a cut. Only a successful end-of-job callback appends one `GS V 0` full-cut command.
- The PDF path has tested one, two, and ten pages; long pages; QR and Japanese glyph *images*; multiple simultaneous submissions; malformed input; and injected capture failure.
- Windows 10/11 and Android/Mopria clients have not been tested. IPP protocol tests use `ipptool` over loopback only.
- Strict rejection of an unsupported `media` value is a known gap: PAPPL 1.3.1 reports `successful-ok-ignored-or-substituted-attributes` for an A4 request, even with `ipp-attribute-fidelity=true`. The gateway cannot recover the discarded original value from the resulting job callback. Do not use this prototype for clients that must be refused by media size.

See [Japanese instructions](README.ja.md), [architecture](docs/architecture.md), [IPP compatibility](docs/ipp-compatibility.md), [safety boundary](docs/safety.md), and [test results](docs/test-results.md).

Phase 0 investigation/design remains in [Draft PR #1](https://github.com/Karin-Laboratory/receipt-printer-web/pull/1). This implementation is a separate branch and PR.

## License

The gateway code follows the repository's MIT license. Third-party dependency notes are in [LICENSE-NOTES.md](LICENSE-NOTES.md).
