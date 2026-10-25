# Safety boundary / NO-GO

1. There is no physical printer sender. The gateway cannot connect to TCP/9100, USB or serial for output. The PAPPL driver exposes only `capture://local`, with device writes always failing.
2. The supported launch path is `scripts/strict_ipp_proxy.py`, bound to `127.0.0.1` and backed by an internal loopback-only PAPPL listener. Directly calling `build/gateway` bypasses strict media validation. This is an **offline trusted-host** arrangement, not authentication or isolation between local users.
3. IPP writes require explicit supported media or the 80mm default. A4/58mm/contradictory `media-col` are rejected before PAPPL normalization. Create-Job/Send-Document and job-attribute update operations currently fail closed. This may exclude clients and must be fixed/tested before Windows/Android interoperability claims.
4. Only PDF and constrained PWG Raster may reach the backend. Bounded request bodies, strict HTTP framing, conversion subprocess timeout and original raster-header checks reduce but do not eliminate malformed-input risks. Poppler parses untrusted PDF under existing CPU/memory limits, not a full sandbox.
5. Whole-job exclusive capture and single successful end-of-job cut event are asserted by integration tests. Captures are private; partial captures are not automatically retried, and a TCP write alone is not proof of physical printing.
6. Do not open LAN ingress, configure Avahi, import a real printer destination, modify CT363, or send ESC/POS/status-query commands to live hardware. Physical Phase 1 and production remain NO-GO.
