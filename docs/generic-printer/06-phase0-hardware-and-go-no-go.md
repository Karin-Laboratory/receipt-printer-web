# Phase 0: 実機仕様・GO/NO-GO

調査日: 2026-10-24。既存サービスの停止/変更、パッケージ導入、プリンタへの印字/紙送り/カット、設定保存/リセットは未実施。

## 実機仕様一覧

| 項目 | 確認結果 | 根拠 / 証拠レベル |
|---|---|---|
| 型番 | TM-T88V系として既存アプリ/運用で扱われている。完全な型番suffixは不明 | 本番コードのdescription・既存資料: OBSERVED。メーカー自己申告応答: UNKNOWN |
| Firmware | 未確定 | HTTP/HTTPS管理面とSNMP `sysDescr` read-only queryは無応答。GS I queryは未実行 |
| 接続経路 | 本番コードが設定宛先のTCP/9100へRAW socket接続 | VERIFIED_STATIC。物理interface board (UB-E03/E04等) はUNKNOWN |
| 管理面 | HTTP/HTTPS port connect timeout、SNMP UDP/161 `sysDescr.0` timeout | OBSERVED。ブラウザ/設定画面へログインしていない |
| 用紙 | 依頼で確定: 80mmロール専用。実機に装填中の紙/プリンタ設定は未確認 | USER-CONFIRMED / UNKNOWN |
| 解像度・印字可能幅 | 180×180 dpi、80mm紙は72.0–72.2mm相当/512 dots (official spec) | VERIFIED_STATIC: [Epson TM-T88V TRG Rev.G](https://download4.epson.biz/sec_pubs/bs/pdf/TM-T88V_trg_en_revG.pdf) |
| オートカッター | 標準TM-T88V仕様はautocutter搭載。実機の状態/設定は未確認 | VERIFIED_STATIC model spec / UNKNOWN device state |
| 現行印刷品質 | 現物を観察していない | UNKNOWN |
| LAN ACL/到達性 | printer admin queryからは不明。9100に対して独立したstatus probeは未送信 | UNKNOWN |

Epsonの仕様では80mmロール幅79.5±0.5mmに対し印字領域は72.2±0.2mm、512 dots、左右余白は各約3.7mm。80mmと72mmは同じ値ではなく、roll widthとprintable widthの差である。[Epson guide](https://download4.epson.biz/sec_pubs/bs/pdf/TM-T88V_trg_en_revG.pdf)

## 512 dotsとアプリ幅536/576の差

画像pixelがそのままraster dotになる本番encoderに対し、`/print`は576 dots、quick-printは536 dotsを生成する。512-dot領域をそれぞれ64 dots (12.5%)、24 dots (4.69%)超過する。576 dotsを180 dpi換算すると約81.3mmで物理80mm roll幅も超える。したがって現状の576/536はTM-T88Vの仕様適合幅ではない。既存実印刷がどうclip/scaleされているかは未確認であり、品質を推測しない。IPP変換は512-dot canvasへ縮小または余白込みで配置する。

## 現行機能とESC/POSコマンド対応

| コマンド/機能 | Bytes / 実装 | 動作・判断 |
|---|---|---|
| Initialize | `1B 40` (`ESC @`) | 各job先頭に送信。プリンタ初期化であり状態を変えるため、遠隔調査に使わない |
| Raster image | `1D 76 30 00 xL xH yL yH data` (`GS v 0`) | 本番encoder。行幅/高さはbyte headerで指定。Epson command referenceはobsoleteとしているがT88V supported-command tableに掲載。[GS v 0](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html) |
| Feed | 4×LFまたは`1B 64 05` (`ESC d 5`) | 各現行経路で異なる。最終feed量と印字位置は未測定 |
| Full cut | `1D 56 00` (`GS V 0`) | Function A full cut。`/print`既定、quick-print、phone eventで使用 |
| Partial cut | `1D 56 01` (`GS V 1`) | Function A partial cut。`/print`の選択肢 |
| Feed + full/partial cut | `GS V 65 n` / `GS V 66 n` | EpsonのFunction B。cut position+n motion unitsまで送りcut。exact n/vertical motion unitを決めるには型番/設定/実測が必要。[GS V](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_cv.html) |
| Status query | `10 04 01..04` (`DLE EOT`) | printer、offline cause、error cause、roll sensorを1byte応答。機械動作を指示しないread-only command。[DLE EOT](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_eot.html) |
| Identity query | `1D 49 n` (`GS I`) | n=1/2/3等でmodel/type/firmware ID。read-only応答。[GS I](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_ci.html) |

### Job単位のcut最終仕様

Epson command specではFunction Aのm=0/48がfull cut、m=1/49がpartial cut。Function Bはn motion units分paperを送り、その後にfull/partial cutする。TM-T88Vのcommand tableに`GS V`があり、standard autocutter modelのcut制御は仕様上存在する。[TM-T88V command list](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/tmt88v.html)

印字headとカッター間距離の図示値は約29mmと約15mmの位置（figure上のtypical値）を示すが、最終feed commandの量へ直接置き換えない。紙の弛み/ロット差を考慮するよう資料が明記する。**実機のfull/partial設定、最終feed量、cut位置、紙送りの最終値は未確定**。自動カット一回の論理仕様は確定できるが、物理的に良い切断位置はPhase 1後の専用実測が必要。[Epson printing/cutting positions](https://download4.epson.biz/sec_pubs/bs/pdf/TM-T88V_trg_en_revG.pdf)

## 完了判定と再送禁止

- `DLE EOT n=1`はonline/offline、`n=2`はoffline reason、`n=3`はrecoverable/autocutter/unrecoverable errors、`n=4`はroll paper sensorを返す。status queryごとに応答を受けてから次を送る。Epsonはreal-time command列を送信データ内へ割り込ませない注意も示している。[Real-time commands](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/realtime_commands.html)
- 単純なTCP `sendall()`成功は紙への印字完了確認ではない。状態応答は機器エラー検知に役立つが、各バイト/jobのcommit receiptや印字完了ACKと同義ではない。exact success barrierは未確定。
- Queue workerがjob全体を排他。全page conversion成功後に順次出力し、ページ境界ではcutしない。ページfilter/backendにcut権限を与えず、job finalizerのみがterminal cutを一度生成する。
- conversion/connection failureやprinter errorではcutを送らずjob failureへ。部分送信後に受理byte位置が不明な場合は`uncertain`状態。全jobを自動再送しない（重複印刷防止）。status確認かoperator recoveryの後に再印刷を判断する。
- 現行アプリにprinter serializerがなく、実機へstatus queryを送るとjob送信に割り込む可能性を排除できないため、DLE EOT/GS Iは実行しなかった。

## IPP Gateway選定: PAPPLを第一候補に確定

**第一選定: PAPPL Printer Application + PDF→PWG Raster変換 + 独自ESC/POS raster encoder**。

PAPPLを選ぶ理由はIPP Everywhere/DNS-SD advertisementと、job-level `rstartjob`/`rendjob` callbacksを提供するため。ページ終端ではfeed/raster継続のみ、`rendjob`が正常な時だけ唯一のcutを出す設計が明快。[OpenPrinting driver callback design](https://openprinting.github.io/documentation/02-designing-printer-drivers) PAPPLはPDFを単独で一般PDF rendererに変換するわけではない。`cups-filters`等でPDF→PWG Rasterを行い、PAPPLのraster input/callbackへ渡す構成を作る。

CUPS custom filterはfilter chainが成熟しPDF変換やspoolに使いやすい一方、古典PPD/shareからIPP clientへadvertiseする機能、filter end-of-job一回だけのcut、全filter/backendにcut命令がないことを検証する必要がある。CUPS filterを比較用capture-only PoCに留め、PAPPLを第一選定とする。既製TM-T88V向け保守済みESC/POS raster driver/filterは確認できなかったため、encoder部分は小規模な独自開発対象。

## リソース評価と隔離試験環境

| CT363監査値 | 値 |
|---|---:|
| CPU | 1 vCPU |
| Memory/swap | 512 MiB / 256 MiB |
| root filesystem | 3.9 GiB total、2.7 GiB available |
| 観測時使用RAM/swap | 21 MiB / 54 MiB |
| systemd service limits | MemoryMax/CPUQuotaの上限なし（Proxmox cgroupは別管理） |

少量の80mm rasterは行ストリーミングすれば小さくできるが、PDF decoder、複数worker、IPP buffers、spool、任意長PDFが追加負荷になる。実ベンチなしに512MiB本番CTが十分とは断定しない。production CTへ導入しない。

### 本番Webを止めない隔離構成

1. agent開発ホスト上の別VM/containerにPAPPL + filterを用意し、本番CTと分離する。
2. 物理printer向けnetwork egressをdeny。backendはESC/POS byte capture sinkに向け、paper movement commandを実機へ送れない構成にする。
3. Windows/Android clientからIPP add、PDF/PWG Raster変換、80mm capability、1文書複数page、filter outputにcut命令が終端一つだけあるかを検証する。
4. malformed/oversized jobs、変換失敗、capture sink途中切断を試し、cutなし・uncertain/no-auto-retry semanticsを確認する。
5. capture-only試験が通ってもphysical printerへ接続しない。実機出力には別プリンタまたは保守枠/排他利用と明示GOが必要。

この環境は本番WebのRAW TCP経路を維持し、IPP/software pipelineだけを先に検証できる。今回実際のVM/container、package、serviceは作成/導入していない。

## 判定

- **IPP gateway software implementation (capture-only): GO**。PAPPL構成、job-boundary cut policy、test isolationが定義された。
- **Production CT installation: NO-GO**。512MiB負荷未測定、本番アプリはCUPSを通らずjob serializerもない。
- **Physical printer output / Phase 1 test page: NO-GO**。型番suffix/firmware/status response/cut/feed state未確認。読み取り専用アクセスはmanagement HTTP(S)/SNMPで応答せず、raw ESC/POS queryは本番直接送信と排他不能なので保留。

物理試験へ進む前に、printer side label/保守画面など印刷を起こさない手段で完全型番を確認し、production printerをexclusiveに利用できる時間または別機を確保する。次にstatus responseと紙feed/cutを明示承認の範囲で検証し、最後にWindows test pageを行う。
