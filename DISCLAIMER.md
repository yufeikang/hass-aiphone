# Disclaimer / 免責事項

[English](#english) | [日本語](#日本語)

---

## English

### No affiliation

This project is an **independent, unofficial** community effort. It is **not affiliated with, endorsed by, sponsored by, or otherwise authorized by Aiphone Co., Ltd. (アイホン株式会社)** or any of its subsidiaries, partners, or distributors.

### Trademarks

"Aiphone", "WP-2MED", "VKZ-R", "VIXUS", and all related product names, logos, and brand identifiers are trademarks or registered trademarks of **Aiphone Co., Ltd.** All other trademarks are the property of their respective owners. Their use in this repository is purely descriptive (nominative fair use) to identify the hardware this software interoperates with, and does not imply any sponsorship or endorsement.

### Origin and methodology

This integration was developed independently through:

- Static analysis of the publicly distributed Android application
- Observation of the user's own network traffic on the user's own equipment
- Independent implementation of the observed wire format

No proprietary documentation, internal source code, signing keys, or non-public cryptographic material was used or distributed. No authentication or licensing mechanism is bypassed: the integration uses the same per-user client certificate that the official application obtains, on the user's own paired device.

### Intended use — personal, non-commercial, on equipment you own

This software is provided **solely for personal, non-commercial use by lawful owners of an Aiphone WP-2MED unit** they have legitimately purchased and physically control, on their own network, with their own paired credentials.

By installing or using this software, you represent and warrant that:

1. You are the lawful owner or authorized administrator of the WP-2MED hardware to which it connects.
2. You will not use it to access, intercept, or interfere with any device, account, or network you do not own or are not authorized to use.
3. You have read and agree to comply with **Aiphone's Terms of Service** for the official mobile application and any other applicable terms governing the device and its cloud services. **Use of this integration may violate those terms; you assume that risk.**
4. You will comply with all laws applicable to your jurisdiction, including but not limited to:
   - **Japan**: 不正アクセス行為の禁止等に関する法律 (Unauthorized Computer Access Law), 著作権法 (Copyright Act), 電気通信事業法 (Telecommunications Business Act).
   - **United States**: Computer Fraud and Abuse Act (CFAA), Digital Millennium Copyright Act (DMCA) including §1201 anti-circumvention provisions.
   - **European Union / United Kingdom**: equivalent computer-misuse, copyright (incl. Directive 2001/29/EC), and electronic-communications statutes.

### No warranty, no liability

This software is provided **"AS IS", WITHOUT WARRANTY OF ANY KIND**, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. See the [LICENSE](LICENSE) for the full MIT terms.

In no event shall the authors or contributors be liable for **any claim, damages, or other liability** — whether in an action of contract, tort, or otherwise — arising from, out of, or in connection with the software, its use, or any related conduct, including but not limited to:

- Property damage, including damage to or loss of access to door entry systems, intercoms, or related home security equipment.
- Loss of data or recordings.
- Service interruption with the manufacturer's official application or cloud services.
- Termination of the user's account or pairing slot by the manufacturer.
- Legal action, regulatory action, or third-party claims of any kind.

The user assumes **all risk** associated with installing and using this software.

### No security guarantees

This integration handles authentication credentials (client certificates, private keys, API responses) and live audio/video data. While the authors have made reasonable engineering efforts, **no security guarantees are made or implied**. The authors are not security professionals; the code has not been audited; vulnerabilities may exist. Users handling sensitive home-security equipment should evaluate the risk for themselves before deployment.

### Removal / takedown

If you are a rights-holder and believe this project infringes a right you own, please open an issue or contact the maintainer. The maintainer will review such requests in good faith and act promptly to remove or modify content as appropriate.

### Severability

If any provision of this disclaimer is held to be unenforceable, the remaining provisions remain in full force and effect.

---

## 日本語

### 提携関係の不存在

本プロジェクトは独立した非公式のコミュニティプロジェクトです。**アイホン株式会社**（Aiphone Co., Ltd.）またはその子会社・関連会社・代理店との提携・推奨・スポンサー関係はなく、何らの認可も受けていません。

### 商標

「Aiphone」「WP-2MED」「VKZ-R」「VIXUS」その他関連する製品名・ロゴ・ブランド識別子は、**アイホン株式会社の商標または登録商標**です。その他の商標も各権利者に帰属します。本リポジトリでの使用は、本ソフトウェアが連携するハードウェアを識別するための記述的な使用（公正利用）にとどまり、いかなるスポンサーシップ・推奨関係をも示唆するものではありません。

### 由来と手法

本統合は以下の独立した手段により開発されました：

- 公開されている Android アプリケーションの静的解析
- 利用者自身が所有する機材における自身のネットワーク通信の観測
- 観測されたワイヤフォーマットの独立した実装

非公開のドキュメント、内部ソースコード、署名鍵、非公開の暗号資産は一切使用・頒布していません。認証および利用許諾の仕組みを回避するものではなく、利用者自身がペアリング済みの機器において、純正アプリと同一の利用者ごとのクライアント証明書を使用します。

### 想定用途 — 個人的・非商業的、所有機器に限定

本ソフトウェアは、**アイホン WP-2MED 本体を適法に購入し物理的に管理する所有者**が、自身のネットワーク上で、自身のペアリング情報を用いて、**個人的・非商業的に利用すること**のみを想定しています。

本ソフトウェアをインストールまたは使用することにより、利用者は以下を表明し保証します：

1. 接続対象の WP-2MED ハードウェアの適法な所有者または認可された管理者であること。
2. 自己が所有しないか、または使用権限のない機器・アカウント・ネットワークへのアクセス・傍受・妨害に使用しないこと。
3. アイホン純正モバイルアプリの**利用規約**およびその他当該機器とクラウドサービスに適用される条件を読み、これに従うこと。**本統合の使用が当該規約に違反する可能性があり、その危険は利用者自身が負担すること**を承知すること。
4. 適用される一切の法令を遵守すること。これには次を含みますがこれらに限られません：
   - **日本**: 不正アクセス行為の禁止等に関する法律、著作権法、電気通信事業法
   - **米国**: Computer Fraud and Abuse Act (CFAA), Digital Millennium Copyright Act (DMCA)（§1201 回避禁止規定を含む）
   - **欧州連合 / 英国**: 同等のコンピュータ不正使用法、著作権法（指令 2001/29/EC を含む）、電気通信法

### 無保証・免責

本ソフトウェアは **「現状有姿（AS IS）」で、明示・黙示を問わず、いかなる保証も伴わずに**提供されます。商品適格性、特定目的適合性、非侵害の保証を含みますがこれらに限られません。詳細は [LICENSE](LICENSE)（MIT ライセンス）を参照。

著作者および貢献者は、本ソフトウェア、その使用、または関連する一切の行為から生じる、これに関連する、またはこれに付随する、**契約・不法行為その他に基づく一切の請求・損害・責任**について、いかなる場合も責任を負いません。これには次を含みますがこれらに限られません：

- 玄関出入口設備、インターホン、関連住宅セキュリティ設備への損害またはこれらへのアクセス喪失を含む財物への損害
- データまたは録画の喪失
- メーカー純正アプリまたはクラウドサービスにおけるサービス中断
- メーカーによる利用者アカウント停止またはペアリング枠の削除
- 訴訟、行政処分、第三者からの請求

利用者は本ソフトウェアの導入・使用に伴う**一切のリスクを自己責任**で負担するものとします。

### セキュリティに関する保証なし

本統合は認証情報（クライアント証明書、秘密鍵、API レスポンス）およびライブの音声・映像データを取り扱います。著作者は合理的な技術的努力を払っていますが、**いかなるセキュリティ保証も明示・黙示を問わず行いません**。著作者はセキュリティ専門家ではなく、コードは監査を受けておらず、脆弱性が存在する可能性があります。住宅セキュリティ機器を扱う利用者は、導入前にリスクを自ら評価してください。

### 削除・取下げ

権利者の方で本プロジェクトが自身の権利を侵害していると考える場合は、Issue を開くか、メンテナまでご連絡ください。メンテナは誠意をもって検討し、適切に内容の削除または修正のため速やかに対応いたします。

### 分離可能性

本免責事項のいずれかの条項が執行不能と判断された場合でも、残余の条項は完全な効力を保持します。
