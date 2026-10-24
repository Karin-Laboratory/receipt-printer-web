# Capture-only 80mm IPPレシートゲートウェイ

IPPジョブを受け付け、512dot幅のESC/POSデータへ変換する隔離プロトタイプです。出力はローカルファイルに固定しています。プリンタIP設定、RAW TCP/9100、USB/シリアル送信機能はなく、PAPPLのデバイス書込callbackも常に失敗します。**ビルド・実行だけで実機印刷はできません。**

PAPPL 1.3系、libcupsのラスタAPI、Popplerの`pdftoppm`を使います。IPP待受は既定で`127.0.0.1`のみ、キュー名は`80mm-capture`、IPPリソースは`/ipp/print`です。

## Debian 13でのビルド・テスト

```sh
sudo apt-get install build-essential pkg-config libpappl-dev poppler-utils cups-ipp-utils python3-pil python3-qrcode fonts-unifont
make
make test
make analyze
make check-capture-only
```

capture専用のIPPサービスを起動する例です。

```sh
install -d -m 700 "$PWD/capture"
./build/gateway --port 8631 --capture-dir "$PWD/capture"
```

captureディレクトリは絶対パス、実行ユーザー所有、mode `0700`が必要です。既定の待受先はloopbackなのでWindows/Android端末からは接続できません。LAN受付、firewall、認証、サービス発見、TLSは別途設計・検証が必要です。

正常終了した文書は`job-N.escpos`、処理記録は`events.jsonl`に保存されます。ファイル権限は`0600`です。失敗jobは完成ファイルとして公開せず、`.partial`を自動再送しません。

## 現在の対応範囲と制限

- PDFは`/usr/bin/pdftoppm`で512dot幅・180dpiの白黒ラスタに変換します。
- PWG RasterはPAPPL標準のstreaming経路で受け付けますが、PAPPL 1.3はこの経路で固定200mmの用紙長を使います。元ページごとに空白行が追加される場合があり、PWG Rasterの可変ページ長は未完成です。
- ページcallbackはカットを出しません。成功したjob終了callbackだけが`GS V 0`を1回追加します。
- PDFの1・2・10ページ、長尺ページ、QRと日本語グリフの画像、並行投入、不正PDF、capture途中失敗を試験しました。
- Windows 10/11、Android/Mopria実機は未検証です。IPP試験は`ipptool`をloopbackに接続して行いました。
- PAPPL 1.3.1は`media=iso_a4_210x297mm`を、`ipp-attribute-fidelity=true`でも`successful-ok-ignored-or-substituted-attributes`として既定媒体へ置換します。job callbackでは破棄前の値を取得できないため、媒体の厳密拒否は未実装です。このまま実運用に使わないでください。

[英語README](README.md)、[構成](docs/architecture.md)、[IPP互換性](docs/ipp-compatibility.md)、[安全境界](docs/safety.md)、[テスト結果](docs/test-results.md)を参照してください。

Phase 0の設計資料は[Draft PR #1](https://github.com/Karin-Laboratory/receipt-printer-web/pull/1)にあります。本実装は別ブランチ・別PRで提出します。
