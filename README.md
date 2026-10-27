# 特定保健指導AI：ステップ1・3

Python 3.12以上、外部Python依存なし。Gemini API上の `gemma-4-31b-it` を使用するファイルベースの初期実装です。モデルをテスト用応答に置き換えた単体テストを含みます。実モデルでの品質検証は別途必要です。

## 実行

APIキーを環境変数 `GEMINI_API_KEY` に設定してください。入力例は実在人物に由来しない合成データです。

```bash
python main.py summary --input examples/synthetic.json --output runs/summary.json
# JSONとMarkdownを原データと照合し、必要ならJSON本文を修正してから承認
python main.py approve --input runs/summary.json --output runs/approved.json --reviewer reviewer01 --note '原データ・警告を確認した記録'
python main.py plan --input runs/approved.json --cards cards.json --output runs/plan.json
python -m unittest discover -s tests -v
```

JSONが正本です。出力先は未使用のパスを指定します。承認済み本文の変更はハッシュ検証で拒否します。旧入力から作った計画の自動失効はまだありません。新版の作成時は利用者が旧成果物を利用対象から外してください。

## 入力

`examples/synthetic.json` を参照。受診ごとに `exam_id`, `exam_date`, `measurements` を指定します。各測定は `source_id`, `code`, `value`, `unit` を持ちます。欠損は `null` と `missing_reason` で表します。比較には `method` と `condition` の一致と明示が必要です。単位変換は行いません。`unknowns`, `questionnaire`, `safety_flags`, `guidance_category` は提供情報を保持します。

## 根拠カード

`cards.json` は以下の構造のカード配列です。以下は形式説明用であり、実際の公的根拠として使用しないでください。原文を確認し、有識者がレビューしたカードを別途用意します。

```json
[{
  "evidence_id": "K001",
  "title": "採用資料名",
  "url": "https://example.invalid/source",
  "edition": "採用版",
  "section": "章・ページ",
  "text": "確認済み原文（条件・脚注を含む）",
  "tags": ["weight"],
  "common": false,
  "conditions": [],
  "reviewed": true,
  "priority": 10
}]
```

現段階は測定コードとタグの一致、または `common` による選択です。条件付きカードの自動適用判定は未実装のため除外します。根拠なし・8枚超過では停止します。カードIDと事実IDを分離し、課題には事実、候補にはカードを引用させます。

## 制約・運用

- ステップ1の数値・差分はコードが生成し、LLMは記述を生成します。制度上の判定・受診勧奨しきい値、BMI再計算は未実装であり、未判定と表示します。
- 自由文の医学的安全性・数値捏造の意味的検出は未実装です。出典IDが有効でも内容が正しい保証はありません。必ず有識者が確認してください。
- 承認コマンドはファイル運用の確認記録であり、認証・電子署名ではありません。入力ファイルのアクセス制御は実行環境で実施してください。
- JSON形式不正・通信失敗時は停止します。自動修復・再試行、実行監査DB、セルフホストアダプタ、画面、ステップ7は未実装です。
- 実データの外部送信は初期状態で拒否します。契約・提供権限・保存条件を確認できた環境だけ `ALLOW_REAL_DATA=1` を設定してください。キー、個人データ、生成結果をGitに登録しないでください。
- MarkdownはJSON全項目を表示する簡易形式です。承認と実行の手順は本番向け権限管理を代替しません。

## ローカルモデル

OllamaのGemma 3 4Bにも対応します。生成コマンドに `--backend ollama` を付けてください。接続先は同一マシンの `127.0.0.1:11434`、モデルの初期値は `gemma3:4b` です。APIキー不要。セットアップと通しの実行例は [デモ手順](examples/demo/README.md#ローカルgemma-3-4bollama) を参照してください。既存のクラウド経路は `--backend gemini`（省略時）です。
