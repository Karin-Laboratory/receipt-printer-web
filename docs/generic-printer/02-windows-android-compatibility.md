# Windows / Android互換性調査

「対応」はIPPゲートウェイを実装した場合の見込みであり、実機相互接続の実証ではない。

## 固定する用紙・ジョブ仕様

- 80mmロール紙専用。A4/58mm mediaを広告・選択対象にしない。
- PDF、Word、Webページ等を80mmロール向けのnative printable widthへ縮小/レイアウトする。
- 1文書の複数ページはページ境界でカットせず、ページ画像を順に連結した1つの連続出力にする。
- 正常完了時にだけESC/POS auto-cutを1回送る。紙送り量とフル/パーシャルカットは正確なTM-T88V型番・設定に基づき決定する。
- 別文書との混在を避けるため、受信から終端カットまでを単一キューの一ジョブとして排他する。

## Windows 10 / 11

MicrosoftはWindows 10 21H2以降、Mopria準拠ネットワーク/USBプリンタ向けMicrosoft IPP Class Driverを提供する。[Microsoft driver servicing](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/end-of-servicing-plan-for-third-party-printer-drivers-on-windows) IPP printerをIP/hostnameで手動追加する導線も案内する。[Microsoft IPP directed discovery](https://learn.microsoft.com/en-us/universal-print/fundamentals/universal-print-connector-with-ipp) ただしUniversal Print Connector資料の条件にMopria認証があり、一般的なIPP応答だけで互換を断定できない。

| 方式 | 通常印刷UI | 追加ドライバ | 80mm/連続文書適合性 | 評価 |
|---|---|---|---|---|
| CUPS + IPP | 条件付きで可能 | IPP class driverを期待 | gatewayが80mm長尺mediaを広告し、ページ連結/filter処理を実装 | 第一候補の互換性検証対象 |
| IPPS | IPP over TLS、証明書信頼設定が必要 | 通常IPP class driver | IPPと同じ媒体/カット仕様 | LAN外経路には推奨。TLS自体はcut制御を加えない |
| Microsoft IPP Class Driver / Mopria | Windows 10 21H2+ / 11のdriverless経路 | 不要になり得る | gatewayがmedia/PDL/attributesを適切に公開する必要 | 条件付き。認証/端末検証を要する |
| Epson Advanced Printer Driver 5.13 | Word/ブラウザなど通常UI | Epson APDが必要 | 型番固有設定を提供しやすいが、文書複数ページを連続して最後に一度だけ切る動作は別途検証 | フォールバック候補。EpsonはTM-T88V APD 5.13のWindows 10/11対応を掲載。[Epson support](https://epson.com/Support/Point-of-Sale/Thermal-Printers/Epson-TM-T88V-Series/s/SPT_C31CA85011?review-filter=Windows+Embedded) |
| RAW TCP 9100 | OS標準queue/自動発見にならない | ESC/POS対応アプリ等が必要 | native dataを生成できる場合のみ | クライアントへ公開しない。gateway内部送信に限定 |
| 独自PDF/画像web gateway | OS標準dialogには通常表示されない | 独自clientが必要 | 80mm変換を制御しやすい | 補助方式 |

PDF/Word等のクライアント印刷では、IPP受付後に標準PDLをrasterへ変換する。IPPを話すだけでは文書形式、長尺媒体、任意ページ境界を超えた連続feed、最終cut位置は保証されない。

## Android標準印刷

Android Print FrameworkではPrint Serviceがprinter discoveryとPrintJob lifecycleを担う。[Android PrintService API](https://developer.android.com/reference/android/printservice/PrintService) Mopriaは同一LANのmDNS自動発見とIP/hostname手動登録を案内する。[Mopria FAQ](https://mopria.org/faq) [Mopria how-to](https://mopria.org/?catid=2&id=11%3Ahow-to-print&view=article)

| 方式 | 標準印刷UI | 手動IP / 発見 | 判定 |
|---|---|---|---|
| IPP Everywhere | 有効なAndroid Print Service/Mopriaがあれば表示可能 | DNS-SD/mDNS広告、サービスによって手動IP | 条件付きで目標適合 |
| Mopria Print Service | インストール/有効化が必要な端末あり | MopriaはIP/hostname手動登録とmDNS探索を案内 | Android標準印刷の第一候補 |
| Android Default Print Service | OEM/OS版依存 | 実装依存 | 端末差があり一律保証できない |
| CUPS経由 | CUPS queueがIPP/Mopriaに適切な属性と発見を提供した場合 | Avahi/DNS-SD、またはservice経由の手動指定 | CUPSを入れるだけでは成立しない |
| 専用PrintService APK | APKを導入・有効化した端末で表示 | 独自実装次第 | ESC/POS固有制御を強化できるが配布/保守が増える |
| 既存Web/通話API | OS print UIではない | API server URL設定 | 現行連携を維持する補助経路 |

ChromeやPDF viewerはアプリ自身がAndroid印刷APIを呼び出す場合に標準print UIを出す。すべてのアプリが印刷ボタンを持つとは限らない。Mopriaもアプリの印刷または共有対応を条件としている。[Mopria how-to](https://mopria.org/?catid=2&id=11%3Ahow-to-print&view=article)

## ページとオートカット

IPPの一般形式にはPDF/PWG Raster等がある。[OpenPrinting driverless](https://openprinting.github.io/driverless) しかし「1 job=1文書=連続ロール=最後に一度だけ切る」はESC/POS filterとqueue側で保証する追加仕様である。各PDFページにcutを割り当てず、全ページを同一spool jobへ保持し、正常な最終送信が完了した後に単一のterminal cut commandを出す。レンダラ/PPD filter/CUPS backendから別cut命令が出ないことも確認する。

通信断時にはESC/POS RAW TCPがプリンタ受理位置を確実に返すとは限らない。送信途中でconnection errorになった時、受理済み先頭データは物理出力済みかもしれないため、同じ全jobの自動再送は二重印刷の危険がある。ジョブを `queued / sending / completed / uncertain-failure` で管理し、部分送信後は自動再送せず、オペレータ判断か状態照会が必要な設計を検討する。正常終了と判断できない状態ではcutを送らない。RAW socket write完了だけをプリンタの印字完了と同義に扱わない。

## 発見と媒体

- mDNS/DNS-SDは通常同一リンク内。VLAN/subnet/VPNでは自動発見しない前提で、reflectorか手動登録を検討する。
- IPPSはTLS/証明書を含む。媒体幅やcut仕様はIPP attributes/filterで別途実装。
- IPP queueのmedia capabilitiesは80mm rollだけを提供し、A4/58mmは公開しない。
- Epson TM-T88V資料上の80mm印字幅は72mm/512 dots。[Epson guide](https://files.support.epson.com/pdf/pos/bulk/tm-t88v_trg_en_revf.pdf) 実機のfirmware/interface、紙送り/カット仕様と不揮発設定は未確認。
- 日本語はサーバ側でフォント描画してraster化する設計がコードページ差を減らす。フォントlicense、縮小率、画像/QR再現性をPhase 3で検証する。

## 結論

Windows/Androidの標準印刷はIPP/Mopria互換のgatewayを設計すれば実現可能性が高い。ただしTM-T88V実機、OS標準印刷サービス、80mm長尺media、複数ページ連結、文書単位の単一cutは未検証であり、実機試験前に保証しない。
