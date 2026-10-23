# 現行システム監査（読み取り専用）

調査日: 2026-10-24。稼働環境の読み取り専用確認と公開リポジトリのソース確認を分けて記す。内部アドレス、認証値、ログ、個人情報は掲載しない。

## 概要

- **OBSERVED**: Debian GNU/Linux 13.6 (trixie) の Proxmox LXC。1 vCPU、512 MiB RAM、256 MiB swap。稼働カーネルはProxmoxホスト由来。
- **OBSERVED**: `receipt-web.service` は監査時点でactive/running。専用 `receipt-web` ユーザー、Gunicorn 2 worker × 2 threadでTCP/80に内部bind。停止・再起動はしていない。
- **OBSERVED**: `/opt/receipt-web` はGit checkoutではない。公開リポジトリ `Karin-Laboratory/receipt-printer-web` の `main` は本番の現在版と同一ではない。
- **OBSERVED**: コンテナ内にCUPS、Avahi、CUPS CLI、Epson CUPSドライバの導入は確認できなかった。追加導入は行っていない。
- **UNKNOWN**: プリンタの完全な型番サフィックス、ファームウェア、Ethernetオプション、媒体設定。プリンタへの照会・接続はしていない。依頼者の確定仕様により、対象媒体は80mmロール紙のみとする。

## 対象と証拠の境界

| 対象 | 確認方法 | 証拠レベル | 注意 |
|---|---|---|---|
| CTのOS/資源/サービス/待受 | SSHでOS情報、systemd、socket、package query | OBSERVED | アドレス値は非公開資料にも転記しない |
| 本番アプリ | ファイル構造、AST、限定したコード行を読み取り | OBSERVED | 秘密値や運用データは記録しない |
| 公開GitHub候補 | clean `main` の履歴・ファイル確認 | VERIFIED_STATIC | 公開版は本番版の完全な履歴ではない |
| プリンタ型番/firmware | 実機・管理画面未照会 | UNKNOWN | TM-T88V系という説明以上を断定しない |

## 本番アプリの印刷経路

**OBSERVED**: 本番版はFlask/Gunicornで、トップ画面、プレビュー、印刷、quick-print、電話イベントAPI、health系endpointを持つ。Pillowで日本語テキスト・画像・QRコードをグレースケール画像へ組み立て、二値化してESC/POSラスタデータに変換し、設定されたRAW TCPプリンタ宛先へ送信する。電話イベントはSQLiteへ重複排除状態を記録する。

**OBSERVED**: 通常印刷は576 px幅、余白24 px（コンテンツ幅528 px）。quick-print経路には別の536 px幅/24 px余白（コンテンツ幅488 px）がある。ラスタの後に紙送りと全切りまたは半切りコマンドを付加する。電話イベント経路にも画像ラスタ、紙送り、全切りの処理がある。

**OBSERVED**: 電話イベントAPIはBearer token検証とUUID/SQLite `BEGIN IMMEDIATE` による重複処理を行う。値、電話番号、イベント内容は掲載しない。

**OBSERVED**: `threading.Lock` / `RLock` やプロセス間共通の物理印刷キューは確認できなかった。SQLite transactionはイベントDB更新を直列化するが、Gunicorn workerをまたいだ印刷全体の直列化は保証されない。ジョブ混在の有無は実運用印刷で未検証。

## 公開リポジトリとの対応

公開 `main` はフォーム文字列をUTF-8でRAW TCP送信し、初期化、改行、全切りを付加する小規模アプリである。画像、QR、電話イベント、SQLite、spoolは含まない。READMEは他機種未検証としている。公開リポジトリは調査文書の置き場所として適切だが、本番ソース同期・履歴監査は別途必要。

本番環境で確認したPython配布物の版はFlask 3.1.1、Gunicorn 23.0.0、Pillow 11.1.0、qrcode 8.2、Werkzeug 3.1.3。完全なSBOMではない。

## 印字幅との整合性

Epson TM-T88V技術資料は80mm紙の印字可能幅を72mm/512 dots、解像度を180 dpiとしている。[Epson TM-T88V Technical Reference Guide](https://files.support.epson.com/pdf/pos/bulk/tm-t88v_trg_en_revf.pdf) 本番画像幅576 pxとquick-print幅536 pxはいずれも512 dotを超える。**INFERRED**: 現設定をそのまま送ると切れや機種依存結果の可能性があるが、実印字未実施のため影響は断定しない。80mm専用の変換器は512-dot幅、左右余白、縦方向の連続データを扱う必要がある。

## CUPS/Avahi/ドライバと管理上の現状

- **OBSERVED**: CUPS、Avahi、Epson CUPSドライバは導入確認なし。LAN向けIPP queueやmDNS広告は確認できない。
- **OBSERVED**: アプリはプリンタへ直接RAW TCP接続し、CUPS spoolerを介さない。
- **UNKNOWN**: LAN firewall、プリンタ側9100制限、VLAN、VPN経路、クライアント到達性。接続試験はしていない。
- **REPORTED**: 既存設定にプリンタRAW TCP 9100宛先がある。プリンタ自体がIPP/Mopriaを提供する証拠ではない。

## 維持すべき互換性

Web画面、quick-print連携、Android通話イベント連携は保持対象。AndroidソースのUploadWorkerは電話イベントAPIへHTTP POSTするもので、`PrintManager` / `PrintService` 実装は見つからなかった。ブラウザ拡張の本番利用説明はあるが、今回確認した公開リポジトリに実装はない。

## 未確認

完全な型番/firmware/interface、80mm媒体設定、カット機構の状態、LAN ACL、現在のジョブ排他、日本語文字のバイト処理、各OS/端末版は未確認。実機印刷、ポート試験、設定変更はしていない。
