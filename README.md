# Receipt Printer Web

English | [日本語](README.ja.md)

A small web interface for sending receipts to a network-connected thermal receipt printer.

## What it does

1. Enter text in a browser.
2. Flask receives the request.
3. The app sends ESC/POS bytes over raw TCP to the configured printer.
4. The printer prints the receipt and cuts the paper.

There is no database, phone integration, account system, or household-specific data in this repository.

## Requirements

- Python 3.10 or newer
- A network thermal printer that accepts raw TCP connections
- An ESC/POS-compatible printer is expected; this implementation has been used with an Epson TM-T88V in the original private environment, but the clean public implementation has not been tested with other models.

## Run locally

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example .env
export $(grep -v '^#' .env | xargs)
flask --app app run
```

Open http://127.0.0.1:5000. Set `RECEIPT_PRINTER_HOST` and `RECEIPT_PRINTER_PORT` for your printer before printing.

For a real deployment, put the environment file outside the repository and keep it out of version control.

## Deployment

`systemd/receipt-printer-web.service.example` is a hardened example. Create a dedicated `receipt-web` user, install the application under `/opt/receipt-printer-web`, create `/etc/receipt-printer-web.env`, and adjust the paths to your installation. The example binds to localhost on port 8000; place it behind a reverse proxy if remote browser access is needed.

Do not expose this application directly to the Internet. It intentionally has no authentication or authorization. Restrict access to a trusted network and consider adding authentication at a reverse proxy.

## Printer protocol

The app opens a TCP connection to the configured host and port (9100 by convention), sends an ESC/POS initialize command, UTF-8 text, line feeds, and a full-cut command. Character encoding and cut behavior vary by printer, so verify them with your model before regular use.

## License

MIT. See [LICENSE](LICENSE).
