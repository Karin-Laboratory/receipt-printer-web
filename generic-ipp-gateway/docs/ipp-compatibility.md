# IPP compatibility and open issues

## Protocol tested

- PAPPL 1.3.1 advertises IPP 1.1/2.0, PDF, PWG Raster, URF, and `mopria-certified=1.3` in its Get-Printer-Attributes response.
- `Get-Printer-Attributes` and `Print-Job` were exercised with CUPS `ipptool` against a loopback listener.
- PDF is the preferred format in the test response and uses the custom conversion callback.
- PWG Raster is accepted through PAPPL's built-in streaming path. The test uses 1-bit black raster; client OS raster variations have not been validated.
- There is no mDNS/Avahi advertisement in this prototype. Clients must be configured with an IPP URI in a later LAN-enabled phase.

## Media behavior gap

The queue advertises only `custom_receipt_80x200mm`, 80 mm media with 3.89 mm left/right margins, continuous tracking, and 180 dpi. The usable width is represented as 512 dots at 180 dpi. It does not support A4 or 58 mm.

PAPPL 1.3.1 accepts an A4 `media` value as ignored/substituted even when the request sets `ipp-attribute-fidelity=true`. Its job object no longer exposes the original unsupported value to the driver callback. The callback validates media values that remain present, but this does not close that PAPPL behavior gap. An IPP front-end validation layer or a PAPPL fix is required before claiming strict rejection.

## Client compatibility status

| Client | Status | Evidence |
| --- | --- | --- |
| CUPS IPP tools | Verified for local attributes and test jobs | CI/local `ipptool` tests |
| Windows 10/11 IPP Class Driver | Not tested | No Windows client in environment |
| Android standard print / Mopria | Not tested | No Android client in environment |
| Automatic discovery | Not implemented | No Avahi/DNS-SD record |

Do not infer OS compatibility from PAPPL's Mopria capability string. Windows/Android printing menus, media choice UI, PDF/Raster format negotiation, and client retries still require tests on those OS versions.
