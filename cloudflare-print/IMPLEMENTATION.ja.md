# Karin Print Cloudflare/Web/MCP 拡張実装

状態：オフラインcapture-only MVP。CT363と実プリンタは変更していない。クラウドへのデプロイも未実施。

## 実装済み
- Cloudflare Worker Web UI。80mmプレビュー、テキスト/Markdown/PDF/PNG/JPEG受付（上限1MiB）、本人による明示確認
- Cloudflare Access JWTのRSA署名・issuer・audience・期限検証。許可ユーザーだけ原稿を閲覧・取消
- D1ジョブ状態とprivate R2原稿保存。ジョブ一意ID・冪等性キー・排他leaseを使用
- Agentは宅内からHTTPSを発信してジョブを取得。ローカルに原稿sourceをfsyncして保存するだけ。ESC/POSや紙への印字なし
- 途中送信やlease期限切れはuncertainとし、自動再送しない
- MCP JSON-RPCのinitialize/tools/list/tools/call、prepare_print・get_print_status・cancel_queued_print
- MCP原稿はブラウザの承認URLを開き本人が印刷確定する。MCP自身は印刷確定ツールを持たない
- Node/PythonテストとGitHub Actions

## 重要な未完了
- Cloudflareアカウントへの公開デプロイ、Accessアプリ・D1・R2・secretsの実設定と実環境試験
- ChatGPTからのMCP接続。OAuthプロバイダ/Access for SaaS連携が未実装。MCPプロトコルの単体試験とChatGPTツール接続は別
- ローカルagentが保存するのは原稿sourceファイル。既存generic-ipp-gatewayのESC/POSへ転送する機能は未接続
- Windows/Android/既存Webも含めた単一物理キューへの統合、本番CT363への導入は未実装
- プリンタの実機型番・紙送り・カット位置・印字完了ACKは未確認

## オフライン試験
cloudflare-print ディレクトリで Node.js 22+ / Python 3.11+ を使用：

    npm run verify
    python3 -m unittest discover -s agent/tests -p 'test_*.py' -v

テストは生成したRSA鍵、模擬D1/R2、ローカルcaptureファイルだけを使用する。実プリンタには接続しない。

## Cloudflareステージングへの導入手順（未実行）
1. 既存Karin-WorkersのGitHubデプロイ規則とCloudflare AccessメールOTPポリシーを確認。
2. 専用staging Worker、D1、private R2、Access applicationを作成しブラウザを本人限定とする。
3. wrangler.example.tomlをコピーしてIDとAccess team domain/audienceを設定。長いランダムAGENT_TOKENをWorker secretに保存し、Gitに入れない。
4. D1 migrationを適用する。WorkerはAccess JWT署名をサーバ側で検証する。
5. Cloudflareと宅内pull-agentを接続する前に、アクセス拒否・CSRF・quota・lease失効の実環境検証を実施する。
6. isolatedホストでローカルcaptureを試し、原稿が物理印刷されないことを確認する。
7. ChatGPT用MCPは認証付きOAuthのdiscoveryと接続権限を別途確認してから、書き込みツールを公開する。

## Agent起動例（staging設定後）

    export PRINT_CLOUD_URL=https://YOUR-WORKER.example
    export PRINT_AGENT_TOKEN=YOUR_SECRET_CONFIGURED_OUTSIDE_GIT
    python3 agent/pull_agent.py --capture-dir /path/to/private-capture --once

上記は原稿sourceを保存する試験であり、紙への印刷ではない。

## 開発時の安全方針
- クラウド上のキューへ入ったことは物理印刷完了と扱わない。
- 重複ジョブ/ambiguous-ackは自動再実行しない。
- 認証なしの印刷APIは公開しない。
- ChatGPTからprepareしただけでは印刷されない。本人がブラウザ承認する。
- 本番CT363、RAW TCP/9100、実プリンタの切替は別途GO判定。

設計：cloudflare-print/README.ja.md。既存IPP：generic-ipp-gateway/。
公式資料：https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/secure-mcp-servers/
