# Aiphone WP-2MED — Home Assistant 統合

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

[English](README.md) | 日本語

> ⚠️ **非公式の独立プロジェクトです — アイホン株式会社とは無関係です。** 使用は自己責任です。インストールまたは使用することで [免責事項（DISCLAIMER）](DISCLAIMER.md)に全面的に同意したものとみなされます。

アイホン **WP-2MED** テレビドアホン（戸建用、[VIXUS / VKZ-R](https://www.aiphone.co.jp/products/business/vkz/) シリーズ）のための Home Assistant 統合です。

純正 iOS / Android アプリと同じ AWS IoT mTLS 経路で WP-2MED 本体と直接通信し、呼び出しイベント、スナップショット、モニター、録画、応答、電気錠解錠を Home Assistant のネイティブエンティティとして公開します。**クラウド中継・スクレイピング・ポーリングは一切なし** — AWS IoT MQTT のプッシュをリアルタイムで受信します。

> **ステータス**: フェーズ 2 機能は作者宅で稼働中。フェーズ 3（応答・解錠）は実装済みだが一部未検証。詳細は [§ ステータス](#ステータス) を参照。

---

## 機能

### センサー

| エンティティ | 種類 | 説明 |
|---|---|---|
| `binary_sensor.<unit>_doorbell` | Occupancy | 呼び出し中に `on` |
| `sensor.<unit>_doorbell_state` | string | `idle` / `ringing` / `answered` |
| `sensor.<unit>_last_caller` | string | 最後の呼び出しの DSP1（通常「玄関1」） |

### カメラ

| エンティティ | 説明 |
|---|---|
| `camera.<unit>_entrance` | JPEG スナップショット — 進行中キャプチャの**ライブフレーム**を優先し、なければ直近の確定済み MP4 から取得 |

### ボタン

| エンティティ | 動作 |
|---|---|
| `button.<unit>_monitor` | 30 秒間のオンデマンドモニター（呼び出し音なし、他の連携端末を煩わせない） |
| `button.<unit>_answer` | `MID 24000 RSLT=200` を送信して現在鳴動中の呼び出しに応答。音声開通、本体の鳴動停止、他端末の通知抑制。 |

### ロック

| エンティティ | 動作 |
|---|---|
| `lock.<unit>_door` | `MID 26021 SET_UNLOCK_REQ` を送信して制御出力（電気錠）を駆動。瞬間動作 — HA は 5 秒後に「locked」へ自動復帰（本体の約 3 秒オートリロックと整合）。 |

### 自動録画

ドアホン呼び出しごとに `/config/aiphone/recordings/<ts>-<caller>.mp4` へ自動録画。モニター利用時は `monitor-<ts>.mp4` として保存。MP4 mux のフラッシュのため、通話終了後 8 秒間は録画継続。

---

## 動作の仕組み

```
WP-2MED ──── AWS IoT Core (Tokyo) ───┐
   │  MQTT mTLS ポート 8883          │
   │  ALPN x-amzn-mqtt-ca            │
                                     ▼
                            HA (本統合)
                                     │
                                     ├─► binary_sensor / sensor
                                     ├─► button (monitor / answer)
                                     ├─► lock
                                     └─► camera + 自動録画 (aiortc)
```

- **ペアリング**: 純正アプリと同一の手順 — LAN UDP ディスカバリ（51711 / 51712）、TLS-52712 によるワンタイムパス交換、HTTPS `/registClient` でクライアント証明書（RSA-2048、2070 年まで有効）を取得、`01005` で表示名を登録。**Home Assistant の設定フロー内で完結** — 外部ツール不要。
- **呼び出しイベント**: `<unit-mac>/#` を購読し、`MID 23001` / `24000` / `24002` を解析してドアホン状態機械を駆動。
- **映像**: 呼び出し（またはモニターボタン押下）時に AWS Tokyo の Janus VideoRoom SFU に対し、Aiphone の SDP-over-MQTT WebRTC ハンドシェイクを実施。`aiortc` をローカル DTLS-SRTP ピアとして使用し、MP4 として録画。パススルー映像トラックにより、ファイル確定を待たずにライブフレームを JPEG として取得可能。

---

## 動作要件

- Home Assistant 2024.3 以降（Python 3.11+）
- 初回ペアリング時、WP-2MED と Home Assistant が同一 LAN 上にあること（以後はインターネット接続のみ）
- `api.aiphone-app.net` への HTTPS 送信（ペアリング時のみ）
- `*.iot.ap-northeast-1.amazonaws.com:8883` への MQTT 送信（定常状態）
- 本体側の連携端末枠に空きがあること（戸建モデル：家族の電話を含めて最大 4 台）

`aiortc>=1.14.0` と `av>=10.0.0` は初回ロード時に自動インストールされます。Raspberry Pi では数分かかる場合があります。

---

## インストール

### HACS（公開後の推奨方法）

1. HACS にカスタムリポジトリとして本リポジトリを追加（カテゴリ：integration）
2. 「Aiphone WP-2MED」を検索してインストール
3. Home Assistant を再起動

### 手動

```bash
# HA 設定ディレクトリ内で
cd config/custom_components
git clone https://github.com/yufeikang/hass-aiphone.git aiphone-tmp
mv aiphone-tmp/custom_components/aiphone .
rm -rf aiphone-tmp
```

Home Assistant を再起動。

---

## ペアリング手順

1. **WP-2MED 本体**: 設定 → 各種設定 → アプリ連携 → 端末追加（または同等の「機器を追加」メニュー）。
2. **Home Assistant**: 設定 → デバイスとサービス → 統合を追加 → 「Aiphone」を検索。
3. 表示名を入力（本体の連携端末リストに表示される名前 — 例：「HA」）。
4. 送信。ペアリングは 5〜10 秒で完了。本体画面の連携端末リストに追加されます。

ペアリングが失敗する場合、以下を確認してください：
- HA と本体が同一 LAN 上にある（UDP ブロードキャストが `255.255.255.255:51711` に到達する必要あり）
- 本体が現在「端末追加」モードである（約 30 秒で自動解除）
- ファイアウォールで `api.aiphone-app.net` への 443 番ポート送信がブロックされていない

---

## ステータス

| 機能 | 状態 |
|---|---|
| HA UI でのペアリング | ✅ 動作 |
| ドアホン呼び出しイベント | ✅ 本番運用中 |
| 呼び出し時の自動録画 | ✅ 本番運用中 |
| `camera.entrance` スナップショット | ✅ 動作 — ライブフレーム + MP4 フォールバック |
| `button.monitor`（オンデマンドカメラ） | ✅ 動作 — 30 秒 MP4 を取得 |
| `button.answer`（24000 RSLT=200） | ⚠️ **実装済み、実呼び出しでの検証未完了** |
| `lock.door`（26021 解錠） | ⚠️ 実装済み、**作者宅では電気錠未配線のため物理動作未確認** |
| 録画への音声収録 | ❌ 未対応 — クラウドは実呼び出し `24000` 後にのみ音声 RTP を開放。応答ボタン検証待ち。 |
| 通話切断 | ❌ 未実装（おそらく `24002 RSLT=603` + `30031` リリース） |
| 双方向音声（TTS / AI 応答） | ❌ 未実装 — PC1 は将来用に audio-sendrecv トランシーバを保持。 |
| HACS 配信 | ❌ 未対応（本 README と `hacs.json` は準備段階） |

---

## 既知の問題

- **初回スナップショット遅延**: 呼び出しから最初の JPEG フレーム取得まで約 3 秒。SDP 交換 + DTLS ハンドシェイクが支配的。この間 `camera` エンティティは前回 MP4 の最終フレームへフォールバック。
- **切断ワークアラウンド**: 切断ボタン未実装。`button.answer` 後、本体タイムアウト（または訪問者の離去）で自然終了。本体が `MID 24002` をブロードキャストしてから 8 秒後に録画停止。
- **マルチクライアントの購読枠**: クラウドは 1 呼び出しにつき購読者を 1 つしか許容しない。純正スマホアプリが先に購読すると HA の録画は `RSLT=400` で映像なしになる可能性あり。実用上は呼び出しから約 100 ms 以内に購読できるためほぼ問題なし。

---

## 開発

```bash
git clone https://github.com/yufeikang/hass-aiphone.git
cd hass-aiphone
uv venv
uv pip install -e ".[dev]"
```

テスト実行（テスト追加後）：

```bash
pytest
```

統合は 2 層構成：

```
custom_components/aiphone/
├── __init__.py            # config-entry セットアップ + v1→v2 マイグレーション
├── manifest.json
├── const.py
├── config_flow.py         # 多段ペアリング UI
├── pairing.py             # ブロッキング LAN UDP + TLS + /registClient フロー
├── coordinator.py         # MQTT (paho-mqtt) + 状態機械
├── media.py               # aiortc; パッシブ + モニター捕獲; ライブフレーム tee
├── binary_sensor.py
├── sensor.py
├── button.py              # モニター + 応答
├── camera.py              # ライブフレーム → JPEG; MP4 フォールバック
└── lock.py                # 26021 解錠
```

プロトコルレベルの質問（ワイヤフォーマット、MID テーブル、エッジケース等）は Issue Tracker にてお願いします。

---

## 謝辞

本プロジェクトは、公開されている Android アプリケーションの静的解析と、著作者自身の機材における自身のネットワーク通信の観測から、ゼロから構築されました。非公開のドキュメント・内部ソースコード・非公開の暗号資産は一切使用していません。公開されている Aiphone SDK は存在しません。

---

## 免責事項

本プロジェクトは**独立した非公式のコミュニティプロジェクト**であり、**アイホン株式会社との提携・推奨・スポンサー関係はありません**。「Aiphone」「WP-2MED」「VKZ-R」「VIXUS」はアイホン株式会社の商標です。

本統合の使用は、メーカーの利用規約に**違反する可能性があり**、その危険は利用者自身が負担します。インストール前に [免責事項（DISCLAIMER）](DISCLAIMER.md)の全文をお読みください。

権利者の方からの取下げのご依頼は、Issue を開くか、メンテナまでご連絡ください。

---

## ライセンス

MIT — [LICENSE](LICENSE) 参照。本コードの使用については、[免責事項（DISCLAIMER）](DISCLAIMER.md)に定める追加の無保証および自己責任利用の条件にも従うものとします。
