# Third-party license notes

The repository is MIT-licensed. These are build/runtime dependencies; no third-party source or binary is copied into this folder.

| Dependency | Use | License note |
| --- | --- | --- |
| PAPPL 1.3.x (`libpappl-dev`) | IPP Everywhere server, job queue, raster callbacks | Apache-2.0; see upstream `LICENSE` and Debian copyright file |
| libcups 2.4.x (`libcups2-dev`) | IPP and PWG/CUPS Raster APIs | Apache-2.0; see upstream CUPS license and Debian copyright file |
| Poppler `pdftoppm` (`poppler-utils`) | PDF rasterization through a child process | GPL-2.0-or-later package family; invoked as a separate system executable and not linked or redistributed here |
| Python qrcode / Pillow | Test fixture generation only | Debian packages `python3-qrcode` (BSD-3-Clause) and `python3-pil` (HPND-like Pillow license); not runtime dependencies |
| GNU Unifont JP | Japanese glyph bitmap test fixture only | SIL Open Font License 1.1; font is read from the system and not copied into this repository |

Versions and license identifiers above were checked against Debian 13 package metadata and copyright files on 2026-10-24. Recheck package notices before redistributing a bundled appliance image. The test suite does not bundle PDF, font, QR, or printer data fixtures.
