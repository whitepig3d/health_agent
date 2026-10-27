# ステップ1・3のダミーデータ

すべて架空の入力と創作した根拠カードです。実在人物の情報や国の公開資料の引用は含みません。顧客に提示する場合も「合成データ・模擬根拠による技術デモ」と明示してください。

| 入力 | 履歴 | 確認する挙動 |
|---|---|---|
| input_a.json | 3回 | 体重・腹囲等の増加から確認質問を作る。原因は断定しない |
| input_b.json | 3回 | 数値の低下を扱う。本人の取り組みや医学的な改善を推測しない |
| input_c.json | 2回 | 体重欠損と血圧測定条件の相違を比較不能として扱う |

`evidence_cards.json` は5枚の模擬カードです。URLは実在する根拠へのリンクではなく、予約ドメイン `example.invalid` を使っています。`reviewed: true` は現在の選択処理を動作させるためのデモ設定です。実際に有識者が承認した資料ではありません。`conditions: []` はカード選択時の機械判定条件がないことを表し、個別の行動目標を無条件で推奨してよいという意味ではありません。

## 実行例

リポジトリのルートで実行します。実モデルを利用するため、`GEMINI_API_KEY` の設定が必要です。

```bash
python main.py summary --input examples/demo/input_a.json --output runs/demo-a-summary.json
# 出力を確認し、必要ならJSONを修正する
python main.py approve --input runs/demo-a-summary.json --output runs/demo-a-approved.json --reviewer demo-reviewer --note '合成データの動作確認。実業務の承認ではない'
python main.py plan --input runs/demo-a-approved.json --cards examples/demo/evidence_cards.json --output runs/demo-a-plan.json
```

B・Cも同じ手順で、入力ファイル名と出力先を変えて実行できます。再実行時は出力名を変えてください。既存ファイルは上書きされません。

実業務や本番PoCでは、このカードを、原文・適用条件・版を確認した公的資料のカードに置き換えてください。本データでの成功は医学的妥当性や公的根拠に基づく提案の実証にはなりません。
