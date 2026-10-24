# Linux印刷バックエンド比較

## 共通仕様

IPPはクライアントとserver間のjob/attributes/status protocol、ESC/POSはTM系レシートプリンタへの最終制御データである。driverlessはクライアント側機種別driverを省けることを意味し、レガシー機に必要なPDF/PWG RasterからESC/POSへの変換を省かない。OpenPrintingはDNS-SD discovery、IPP capability inquiry、standard PDL、server-side filtersを説明する。[OpenPrinting driverless](https://openprinting.github.io/driverless)

固定要件: 80mm専用、A4/58mm非対応。各文書を一つのspool jobとし全ページを連続出力する。正常終了時の最後にauto-cutをちょうど1回。page boundaryでは切らない。job全体を排他し、失敗/通信断時に成功cutや危険な自動再送をしない。

## 案比較

| 案 | 実現性・保守性 | Client互換性 | 問題 |
|---|---|---|---|
| A. CUPS + Epson ESC/POS driver | 古典CUPS filter/PPD構成は可能性あり。現行Debian向けに保守される公式ESC/POS driverは今回特定できなかった | driverless sharingは別途確認 | PPD、native 80mm長尺、page concatenation、終端cut single-shot、版/ライセンス |
| B. CUPS + raster-to-ESC/POS filter | PDF/PWG Rasterを1-bit rasterにし既存ESC/POSに接続可能。custom filterの保守が必要 | CUPS queueがIPP attributes/形式を適切に公開すれば候補 | page毎のcut命令を排除し文書終端だけcut、可変長page stitch、異常終了時cut抑止が核心 |
| C. CUPS IPP受信 + 既存receipt-web renderer | Pillow/QR/日本語描画を活用できる。ローカルIPP submission adapter/filterの追加が必要 | CUPS front-end経由でOS standardを狙える | 現rendererはWeb request context、複数width固定値、直接RAW送信に依存。PDF任意page/文書stitchへ分離が必要 |
| D. 独立IPP server + ESC/POS | 属性・発見・job lifecycleを最大限制御するが実装保守負荷が高い | 仕様準拠ならWindows/Android双方 | IPP/認証/証明書/queue/statusまで独自保守する必要 |
| E. PAPPL Printer Application + ESC/POS filter | **推奨**。IPP Everywhere/DNS-SDとrstartjob/rendjob callbackを使い、job単位のterminal cutを一箇所で所有できる | Driverless clientを狙える | PAPPLはTM-T88V driverではない。80mm job layout/連続feed/cut/失敗制御を独自検証 |

CUPSの古典PPD/driverは非推奨で、OpenPrintingはIPP Everywhere/Printer Applicationを推奨する。[CUPS driver guidance](https://openprinting.github.io/cups/drivers.html) CUPSの`socket` backendはRAW送信transportであり、文書変換機能ではない。[CUPS admin](https://openprinting.github.io/cups/doc/admin.html)

## フィルタ/キュー処理

| 段階 | 入力→出力 | 要件 |
|---|---|---|
| Client | PDF/IPP attributes → IPP job | 80mm rollのみ選択可 |
| IPP spool | complete job dataを一単位として保持 | 同時jobをFIFO/明示schedulerへ |
| Document renderer | PDF pages → sequential raster stream | 各pageをscale/layout。ページ間feedはしてもcutしない |
| Media normalization | page rasters → 512-dot width 1-bit continuous canvas/scanlines | 横余白を保持し縦長上限/メモリを制御 |
| ESC/POS encoder | image/feed commands + one terminal cut | page callbackごとにcutしない。最後まで処理し成功判定後に1 command |
| network writer | bytes → printer RAW TCP | write error後はjob `uncertain`。部分印刷の自動再送不可 |

PWG Rasterはページ単位の形式で、無限長ロールと同義ではない。各ページを同じIPP job内で処理し、カットなしで連結するか、改ページ間のfeedを維持しつつ一文書として排他する。CUPS Raster APIはfilter chain用のページ画像APIを提供する。[CUPS Raster API](https://openprinting.github.io/cups/doc/api-raster.html)

## PAPPLとライセンス

PAPPLはIPP Everywhere service、PDF/image/raster形式、DNS-SD、ネットワーク接続を提供するframework。[PAPPL](https://github.com/michaelrsweet/pappl) OpenPrintingはPrinter Applicationをlegacy printerにIPP interfaceを足す方法として推奨する。[Printer Applications](https://openprinting.github.io/upcoming-technologies/01-printer-application) PAPPLは対応driverそのものではなくprinter-specific filter callbackが必要。[Driver design](https://openprinting.github.io/documentation/02-designing-printer-drivers)

`pappl-retrofit`は既存classic CUPS driversをIPP application化できるが、対象driverが必要。[pappl-retrofit](https://github.com/OpenPrinting/pappl-retrofit) 今回は保守状況を確かめられたTM-T88V用ESC/POS filterを特定できなかった。小規模第三者repoはlicense/maintenance/model support確認前に採用しない。

CUPS/PAPPLはApache-2.0系。[CUPS](https://openprinting.github.io/cups/) [PAPPL](https://github.com/michaelrsweet/pappl) 独自encoder、font、PDF rendererのlicenseは個別確認。Epson APDはWindows向け商用softwareの配布条件を別途守る。

## Debian 13 / resource

Debian 13でCUPS、Avahi、PDF/raster toolsを利用する構成は想定可能だが、このCTは1 vCPU/512 MiB。常駐サービスとPDF rendering、spool領域への影響を隔離環境で計測する必要がある。現在未導入であり今回installしていない。CUPS/PAPPLの導入だけでpage concatenation、single cut、error semanticsは実現しない。

## 評価

**Eを第一候補として確定**する。PAPPLのrstartjob/rwriteline/rendjob modelがdocument job境界で終端処理を1箇所へ置ける。PDF受信はcups-filtersの変換器を利用し、PWG RasterをPAPPLへ渡す。CUPS custom filterはcapture-only隔離PoCに限って比較し、client compat/PPD attributes/job end/cut injectionを確認する。既存renderer reuseはWeb経路のadapterとして用い、OS document rendererの代替にしない。Job lifecycleが「1文書1spool job・全page連結・terminal cut一回・partial-send uncertain」で満たせなければ本番採用しない。
