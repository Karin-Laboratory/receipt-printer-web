# Setup notes

The application is intentionally small and can be run by a normal user during development.

For a service installation:

1. Create a dedicated unprivileged service account.
2. Create a virtual environment and install `requirements.txt`.
3. Copy `config/.env.example` to a root-readable environment file and set the printer address.
4. Install and review the example systemd unit before enabling it.
5. Put a reverse proxy with authentication in front if users outside the trusted LAN need access.

The service unit uses `ProtectSystem=strict` and does not require a writable application directory. No database or runtime data directory is needed by this minimal application.
