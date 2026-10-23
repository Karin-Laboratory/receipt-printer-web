# 実装フェーズ計画

今回の範囲は調査・設計のみ。本番変更、service restart、package導入、プリンタへのデータ送信は行っていない。

| Phase | 作業・条件 | 確認項目 / 成功判定 | ロールバック |
|---|---|---|---|
| 0. 監査/バックアップ設計 | 実装前に型番suffix/firmware/interface、media設定、CT制限、network ACLをread-only確認。app/unit/SQLite/config/filter/queue/firewallのbackup/restore手順作成。CUPSとPAPPL PoCを隔離環境で比較 | 80mm native width、feed/cut command、full/partial cut仕様、single terminal cut、正常終了境界、uncertain job手順が確定。復元手順をレビュー | 本番に触れない。隔離PoCを破棄 |
| 1. Windows test page | Phase 0、backup、限定LAN/保守時間、test queue作成が揃う | Win10 21H2+/Win11からmanual IPP add、通常dialog印刷、IPP attributesは80mmだけ、A4/58mmなし。単一ページは正常終了時1回cut。複数job混在なし | test queue/IPP port/advertisement停止。旧Web経路維持 |
| 2. Android標準印刷 | Phase 1成功後、Mopriaまたは標準Print Serviceを使用 | mDNS discovery、手動IP fallback、Chrome/PDF viewer print UI、80mm設定、1文書1cut。mDNS不通でもmanual setup可 | Avahi/IPP test queue停止。client serviceを無効化 |
| 3. 日本語/画像/PDF品質 | Phase 1/2後、safe test contentと保守枠 | CJK glyph/line wrap, image levels, QR scan, PDF scaling/orientation, multi-page continuous roll, no page cuts, end feed/cut position。font license確認 | filter/media configを前版へ戻しtest jobs削除 |
| 4. 用紙/余白/cut調整 | 型番とguide確認後 | 80mm限定、512-dot printable area、左右余白、feed、full/partial cut候補、文書終端一度だけ、再現可能preset。実測とコード解析両方 | 設定前backupへ復帰。変更した不揮発値も記録値へ戻す |
| 5. Web queue統合 | Phase 1–4安定、既存API/UI互換項目確定 | Web text/image/QR/quick-print/phone eventsを同一queueへ。単一spoolによる排他、各documentのsingle final cut、SQLite idempotency、worker横断混在なし。途中切断時cutなし/uncertain表示/自動二重再送なし | app/systemd変更前版へ戻しdirect route復帰。queue停止。DB migration可逆 |
| 6. 運用/discovery/VPN | Phase 5後の承認 | spool容量/retention、queue health、log匿名化、reboot復旧、同一LAN Avahi、VLAN/manual fallback、tailnet ACL/IPPS、TLS trust。WAN無認証公開なし | mDNS/IPP/IPPS広告とACLを戻しLAN限定。queue/webを既知安定版へ復帰 |

## 追加カット検証項目

- CUPS filter chain/backend全体のbyte streamまたはfilter sourceを調査し、ページごとのcutがないことを確認する。
- テスト文書内に複数ページがある場合も連続feedで、terminal cut commandが一個だけであることを検証する。
- conversion error、socket connect失敗、途中write failureの各状態でnormal success/cutにならない。
- 部分送信でプリンタが何を受理したか不明な場合は `uncertain` とし、全jobを無条件再送しない。
- printer status/ACKが使えるか正確なmodel/firmwareで確認。TCP `sendall`成功を物理完了と誤認しない。
- job境界でscheduler lockを保持し、後続文書を先行文書終端まで送信しない。

## Phase 1 判定

**現在はNO-GO**。今回が調査のみであることに加え、完全な型番/firmware、paper configuration、印刷成功ACK/エラー境界、80mm feed/cutの実機基準が未確定。次回、Phase 0のバックアップ/rollback、限定保守枠、隔離IPP queue、Windows test client、テスト用紙が揃えば、既存Web経路を保持したままPhase 1へGO判定できる。