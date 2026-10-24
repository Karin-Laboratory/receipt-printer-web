# Safety boundary

- Physical printer access is absent by design. There is no printer host/port option and no TCP/9100, USB, or serial sender.
- The queue uses only `capture://local`; any other device URI is rejected in the driver callback.
- The listener defaults to `127.0.0.1`. PAPPL has no web administration UI enabled by this application.
- The accepted capture path must be local-looking, absolute, private, user-owned, and not a symlink at its final component. The application only uses local file APIs.
- Test jobs connect only to loopback. They never access CT363 or a physical printer.
- The production `gateway` build does not contain failure-injection environment controls. `gateway-test` contains a compile-time-only `GW_TESTING` byte-count failure hook.
- The PDF converter is a subprocess with CPU, address-space, file-size, and descriptor limits. It is not a complete security sandbox, and Poppler parses untrusted documents.
- Do not expose unauthenticated IPP to the Internet. A LAN listener, firewall allowlist, authentication, TLS, service discovery, and resource limits must be designed before enabling remote clients.
- IPP failure after bytes were written leaves the physical outcome unknowable in a future transport implementation. This capture-only prototype discards partial files and does not retry jobs automatically.

`make check-capture-only` statically checks application source for outbound socket APIs and verifies the exact capture URI. Integration tests bind to loopback only. The source has no physical egress path; this does not replace a network namespace or firewall test in a future network-enabled deployment.
