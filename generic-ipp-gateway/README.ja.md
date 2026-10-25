# 80mmレシートプリンタ向け IPP capture-only ゲートウェイ

Windows/Android向けIPP受付・PDF/PWG Raster→512ドットESC/POS変換の**オフライン開発版**。物理プリンタ接続、TCP/9100、USB送信は実装していない。既存CT363および本番Web印刷には変更なし。

## ビルド・テスト（Debian 13）

```sh
sudo apt-get install build-essential pkg-config libpappl-dev zlib1g-dev poppler-utils cups-ipp-utils python3-pil python3-qrcode fonts-unifont
make
make test
make analyze check-capture-only
```

## 安全な起動方法（重要）

```sh
install -d -m 700 "$PWD/capture"
python3 scripts/strict_ipp_proxy.py --port 8631 --capture-dir "$PWD/capture"
```

IPP受付は `127.0.0.1:8631/ipp/print`、PAPPL内部は `127.0.0.1:8632`。必ず**入口のstrict_ipp_proxy.py経由**で利用すること。直接 `build/gateway` を起動するとPAPPLが非対応媒体を既定値に置換するため、媒体拒否を迂回できる。内部ポートも同一ホストの他プロセスから到達可能なので、この版を信頼できない共有ホスト・LANへ公開しない。

出力は`capture/job-N.escpos`と`events.jsonl`だけ。ジョブごとに排他し、各ページの間にはカットを入れず、正常終了した1文書の末尾に一度だけ`GS V 0`を追加する。途中失敗は未完了データを破棄し、自動再送しない。物理的な印字完了保証とは異なる。

## 受け付ける形式・媒体

- `Print-Job`によるPDFと1bit・512dot幅のPWG Raster（K/W）。PDFはPopplerでラスタ化する。
- PAPPL 1.3のPWG入力には固定200mm長へ補正される性質があるため、**受付前に元PWGを独立コンバータで正確なページ高さのPDFへ変換**してから既存のPDF経路へ渡す。白行を推測で削らず、意図した余白も保持する。
- 明示した媒体`media`または`media-col`は80mmを検証。A4/58mm、矛盾する名称と寸法、不正な属性はIPPエラーで拒否。媒体未指定は80mmキューの既定値として許可する。
- `Get-Printer-Attributes`、`Get-Jobs`など一部読み取り・Cancel-Jobを転送する。**Create-Job/Send-Document、属性変更操作は現在拒否**する。既存のIPPクライアントによってはこの制限で利用できない。

制約：最大約64MiB/ジョブ、最大200ページ、ページ高さ65535ドットまで。PWGは1bit・512dots限定。PAPPLの端末に既に固定200mm長で生成されたPWGの意図した真の余白長は推定できない。

## 未検証・NO-GO

- Windows 10/11の標準IPPドライバ、Android/Mopria実機からの接続・互換
- mDNS/Avahi発見、LAN受付、TLS、認証、複合ジョブ形式
- 物理プリンタの完全型番、紙送り/カット位置、印字品質、ステータス照会・完了ACK
- 本番CT363への導入と物理印刷

**実機接続・本番移行はNO-GOを維持。** この版の合格はloopback IPPとcaptureファイルのテストだけを意味する。

[設計](docs/architecture.md)・[安全境界](docs/safety.md)・[テスト結果](docs/test-results.md)・[英語版](README.md)・[依存ライセンス](LICENSE-NOTES.md)を参照。Phase 0の調査は[Draft PR #1](https://github.com/Karin-Laboratory/receipt-printer-web/pull/1)、実装はDraft PR #2。
