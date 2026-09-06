# Receipt Printer Web

[English](README.md) | 日本語

ネットワーク接続されたサーマルレシートプリンタへ、ブラウザから文字を送る小さなWebアプリです。

## できること

1. ブラウザに印刷内容を入力
2. Flaskがリクエストを受信
3. raw TCPで設定済みプリンタへESC/POSデータを送信
4. レシートを印刷してカット

データベース、電話連携、アカウント機能、家庭固有の情報は含みません。

## 必要なもの

- Python 3.10以降
- raw TCP接続を受け付けるネットワークサーマルプリンタ
- ESC/POS互換機を想定しています。元の非公開環境ではEpson TM-T88V系を使用していましたが、公開版を他機種で検証したわけではありません。

## 最短手順

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example .env
# .envのRECEIPT_PRINTER_HOSTとRECEIPT_PRINTER_PORTを編集
export $(grep -v '^#' .env | xargs)
flask --app app run
```

ブラウザで http://127.0.0.1:5000 を開きます。実運用では`.env`をリポジトリ外に置いてください。

## systemd運用

`systemd/receipt-printer-web.service.example`はhardeningを含む例です。専用ユーザーを作り、アプリの配置先と環境ファイルの場所を環境に合わせて調整してください。例ではlocalhostの8000番で待ち受けます。

このアプリには認証機能がありません。インターネットへ直接公開せず、信頼できるネットワークに限定するか、リバースプロキシ側で認証を追加してください。

## 通信方式

設定したホストとポート（慣例的に9100番）へTCP接続し、ESC/POS初期化、UTF-8テキスト、改行、全カット命令を送信します。文字コードやカット命令の扱いは機種差があるため、利用前に確認してください。

## ライセンス

MIT Licenseです。詳細は[LICENSE](LICENSE)を参照してください。
