# 現行システム監査（読み取り専用）

調査日: 2026-10-24。稼働環境の読み取り専用確認と公開リポジトリのソース確認を分けて記す。内部アドレス、認証値、ログ、個人情報は掲載しない。

## 概要

- **OBSERVED**: Debian GNU/Linux 13.6 (trixie) の Proxmox LXC。1 vCPU、512 MiB RAM、256 MiB swap。稼働カーネルはProxmoxホスト由来。
- **OBSERVED**: `receipt-web.service` は監査時点でactive/running。専用 `receipt-web` ユーザー、Gunicorn 2 worker × 2 threadで稼働。監査時のsocket一覧ではTCP/80が `0.0.0.0` でlistenしていた。systemd/CT設定に独自制限があるかは別途確認が必要。停止・再起動はしていない。
- **OBSERVED**: `/opt/receipt-web` はGit checkoutではない。公開リポジトリ `Karin-Laboratory/receipt-printer-web` の `main` は本番の現在版と同一ではない。
- **OBSERVED**: コンテナ内にCUPS、Avahi、CUPS CLI、Epson CUPSドライバの導入は確認できなかった。追加導入は行っていない。
- **UNKNOWN**: プリンタの完全な型番サフィックス、ファームウェア、Ethernetオプション、媒体設定。アプリ設定のプリンタ宛先にHTTP/HTTPS接続とSNMP sysDescr GETを試したが応答なし。依頼者の確定仕様により、対象媒体は80mmロール紙のみとする。

## 対象と証拠の境界

| 対象 | 確認方法 | 証拠レベル | 注意 |
|---|---|---|---|
| CTのOS/資源/サービス/待受 | SSHでOS情報、systemd、socket、package query | OBSERVED | アドレス値は非公開資料にも転記しない |
| 本番アプリ | ファイル構造、AST、限定したコード行を読み取り | OBSERVED | 秘密値や運用データは記録しない |
| 公開GitHub候補 | clean `main` の履歴・ファイル確認 | VERIFIED_STATIC | 公開版は本番版の完全な履歴ではない |
| プリンタ型番/firmware | 実機・管理画面未照会 | UNKNOWN | TM-T88V系という説明以上を断定しない |

## 本番アプリの印刷経路

**OBSERVED**: 本番版はFlask/Gunicornで、トップ画面、プレビュー、印刷、quick-print、電話イベントAPI、health系endpointを持つ。Pillowで日本語テキスト・画像・QRコードをグレースケール画像へ組み立て、二値化してESC/POSラスタデータに変換し、設定されたRAW TCPプリンタ宛先へ送信する。電話イベントはSQLiteへ重複排除状態を記録する。

**OBSERVED**: 通常印刷は576 px幅、余白24 px（コンテンツ幅528 px）。quick-print経路は別の536 px幅/24 px余白（コンテンツ幅488 px）。両方とも幅の単位は画像pixelで、現行encoderは各pixelを印字dotとしてESC/POSにする。

| 経路 | 機能 | 画像幅 | 出力終端（静的コード） |
|---|---|---:|---|
| `/print` | title/body、配置、サイズ調整、アップロード画像、QR、1–20 copies | 576 px | 4 LF後、full `GS V 0` または partial `GS V 1` |
| `/api/quick-print` | text、title、timestamp、URL QR | 536 px | `ESC d 5`、full `GS V 0` |
| `/api/v1/phone-events` | 着信/電話イベント、番号/連絡先/時刻/応答/留守電transcript、重複イベント処理 | helper依存 | 4 LF後、full `GS V 0` |

日本語はNoto Sans CJKのregular/bold fontで画像描画される。画像とQRもPillowでラスタ化する。電話イベントの同一UUIDはSQLite状態で重複抑止し、未印字transcript追記を扱う。

**OBSERVED**: 電話イベントAPIはBearer token検証とUUID/SQLite `BEGIN IMMEDIATE` による重複処理を行う。値、電話番号、イベント内容は掲載しない。

**OBSERVED**: `threading.Lock` / `RLock` やプロセス間共通の物理印刷キューは確認できなかった。SQLite transactionはイベントDB更新を直列化するが、Gunicorn workerをまたいだ印刷全体の直列化は保証されない。ジョブ混在の有無は実運用印刷で未検証。

## 公開リポジトリとの対応

公開 `main` はフォーム文字列をUTF-8でRAW TCP送信し、初期化、改行、全切りを付加する小規模アプリである。画像、QR、電話イベント、SQLite、spoolは含まない。READMEは他機種未検証としている。公開リポジトリは調査文書の置き場所として適切だが、本番ソース同期・履歴監査は別途必要。

本番環境で確認したPython配布物の版はFlask 3.1.1、Gunicorn 23.0.0、Pillow 11.1.0、qrcode 8.2、Werkzeug 3.1.3。完全なSBOMではない。

## 印字幅との整合性

Epson TM-T88V技術資料は80mm紙の印字可能幅を72mm/512 dots、解像度を180 dpiとしている。[Epson TM-T88V Technical Reference Guide](https://download4.epson.biz/sec_pubs/bs/pdf/TM-T88V_trg_en_revG.pdf) 本番画像幅576 pxとquick-print幅536 pxはいずれも512 dotを超える。差はそれぞれ64 dots（12.5%）、24 dots（4.69%）。576 dotsは180 dpi換算で約81.3 mmとなり、紙幅80 mmをも超える。**INFERRED**: 512-dot printable areaより広い画像はclip/firmware依存になる可能性が高いが、既存実印字品質は今回未観測。576/536はアプリ側canvas幅であり、プリンタの仕様値ではない。80mm専用変換器は512-dot以下へlayoutする必要がある。

## CUPS/Avahi/ドライバと管理上の現状

- **OBSERVED**: CUPS、Avahi、Epson CUPSドライバは導入確認なし。LAN向けIPP queueやmDNS広告は確認できない。
- **OBSERVED**: アプリは設定された宛先のTCP/9100へ直接RAW接続し、CUPS spoolerを介さない。管理HTTP(S) TCP/80,443とSNMP sysDescr/UDP161の読み取り照会は応答しなかった。安全側に倒し、9100上のstatus/IDコマンドは既存直接印刷と競合しうるため送信しなかった。
- **UNKNOWN**: LAN firewall、プリンタ側9100制限、VLAN、VPN経路、クライアント到達性。接続試験はしていない。
- **REPORTED**: 既存設定にプリンタRAW TCP 9100宛先がある。プリンタ自体がIPP/Mopriaを提供する証拠ではない。

## 維持すべき互換性

Web画面、quick-print連携、Android通話イベント連携は保持対象。AndroidソースのUploadWorkerは電話イベントAPIへHTTP POSTするもので、`PrintManager` / `PrintService` 実装は見つからなかった。ブラウザ拡張の本番利用説明はあるが、今回確認した公開リポジトリに実装はない。

## 未確認

実機仕様・状態コマンド

| コマンド | ESC/POS bytes | Epson資料の説明 | 実装判断 |
|---|---|---|---|
| Initialize | `1B 40` (`ESC @`) | printer initialize | 本番各job先頭で使用。状態を再初期化するためstatus照会とは別 |
| Raster image | `1D 76 30 00 ...` (`GS v 0`) | raster bit image。現行資料ではobsolete扱い | 80mmは512 dots以下にする。将来は新graphics commandも候補 |
| Feed lines | `1B 64 05` (`ESC d 5`) または4×LF | print/feed | quick-printはESC d 5、他経路は複数LF |
| Full cut | `1D 56 00` (`GS V 0`) | Function A full cut | 本番全経路で利用あり |
| Partial cut | `1D 56 01` (`GS V 1`) | Function A partial cut | `/print`で選択可能 |
| Feed + cut | `1D 56 42 n` (GS V 66 n) partial, `1D 56 41 n` (GS V 65 n) full | Function B feeds to cut position + n motion units and cuts | Epson generic ref documents this form; exact n/model configuration is unverified |
| Status | `10 04 n` (`DLE EOT`, n=1..4) | realtime printer/offline/error/roll-sensor status | non-paper-motion query; not issued because existing raw path has no exclusion/serialization |
| Printer ID | `1D 49 n` (`GS I`) | model/type/firmware ID query | supported by T88V docs, but not issued for same concurrency reason |

**最終カット仕様**: T88Vの標準仕様ではautocutterあり。Epson command referenceは`GS V 0` full cutと`GS V 1` partial cutをサポート、Function Bでは指定量を送ってからcutする形を示す。[GS V reference](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_cv.html) 実機で設定されているcut mode、終端feed量、knife position、実際のcut結果は未確定。技術資料上、headからautocutterまで約29 mmという図示値はtypicalで、job feedとして固定値に直結してはならない。[TM-T88V Technical Reference Guide](https://download4.epson.biz/sec_pubs/bs/pdf/TM-T88V_trg_en_revG.pdf)

**完了判定/再送**: `DLE EOT n=1`はオンライン/オフライン、`n=2`はoffline cause（紙切れ停止等）、`n=3`はrecoverable/autocutter/unrecoverable error、`n=4`はroll paper sensorを報告する。[Epson DLE EOT reference](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_eot.html) 対応bitは機種設定に依存する。送信途中のsocket失敗は既に受理されたbytes数を保証しないため `uncertain` とし、全体自動再送禁止。成功ACK/印字完了の確実な検知方式は未確定。カット命令の送信前にconverter/network jobが正常終了していることを確認し、失敗ならcutを発行しない。

## 未確認

完全な型番/firmware/interface、80mm設定、カット機構/紙送り設定、LAN ACL、現在の印刷品質、日本語の印字品質、status response、IPP/Mopria client相互運用性は未確認。紙送り/印字/cut/設定変更は行っていない。
