# Changelog

All notable changes to Ping CRM will be documented in this file.

## [Unreleased]

## [1.1.0] - 2026-03-17

### テーマ: ダークモード対応

**全画面・全コンポーネントにダークモードを追加。目に優しいナイトモードで、夜間の利用が快適に。**

---

#### 1. テーマ切り替えトグル

**今まで**: ライトモード固定。夜間や暗い環境では画面が眩しく、目の疲れの原因に。

**今後**: ナビバーに Sun/Moon ピルトグルを設置。ワンクリックでライト/ダーク切り替え。

- OS のシステム設定（`prefers-color-scheme`）を自動検出
- 選択は `localStorage` に保存、次回訪問時も維持
- ページ読み込み時のフラッシュ（FOUC）防止スクリプト内蔵

#### 2. 全ページのダークモード対応

**今まで**: 白背景 + stone 系カラーのライトテーマのみ。

**今後**: Dashboard、Contacts、Settings、Suggestions、Notifications、Organizations、Identity、Auth、Onboarding — 全 20 ルートがダークモードに対応。

- ページ背景: `stone-50` → `stone-950`
- カード: `white` → `stone-900`
- ボーダー: `stone-200` → `stone-700`
- テキスト: コントラスト比 4.5:1 以上（WCAG AA 準拠）

#### 3. 全コンポーネントのダークモード対応

**今まで**: 共有コンポーネント（タイムライン、メッセージエディタ、CSV インポート等）はライトモード前提。

**今後**: 11 個の共有コンポーネントすべてに `dark:` バリアントを追加。

- Nav、EmptyState、ScoreBadge、ContactAvatar、Timeline
- MessageEditor、CsvImport、EditableField、InlineListField
- TagTaxonomyPanel、ActivityBreakdown、CompanyFavicon

#### 4. ブランドカラーの維持

**今まで**: Teal + Stone のブランドパレット。

**今後**: ダークモードでも Teal アクセントを維持。明るさを調整して暗い背景でも視認性を確保。

- アクティブリンク: `teal-700` → `teal-400`
- アクセント背景: `teal-50` → `teal-950`
- ステータスカラー（emerald/amber/red/sky）も同様に調整

---

## [1.0.0] - 2026-03-05

Initial release of Ping CRM.
