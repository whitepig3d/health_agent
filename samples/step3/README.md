# 指導計画案エージェントの入力サンプル

[詳細設計書](../../03_指導計画案エージェント詳細設計書.md)の第5章に対応する、実在人物に由来しない合成データ。全件「模擬入力による技術実演」用であり、有識者による実承認・医学的評価は未実施。`reviewed_findings`も模擬レビューの設定である。

| ファイル | 設定 | 確認する挙動 |
|---|---|---|
| [case_a.json](case_a.json) | 3回の健診で体重72→74→76kg、腹囲87→89→91cm。生活習慣は不明 | 変化を取り上げ、原因を断定せず質問につなぐ |
| [case_b.json](case_b.json) | 体重80→78→76kg、腹囲96→94→92cm。脂質に関する面談課題が残る設定 | 減少した事実も扱い、一律に悪化としない |
| [case_c.json](case_c.json) | 血糖の測定条件が不一致。受診状況の確認が必要な模擬注意事項あり | 血糖の改善・悪化を判断せず、注意事項を保持し、運動量の具体化を保留する |

## 入力方法と範囲

各JSONを1対象者の独立した入力として使用する。生の健診履歴の要約をモデルに依頼する入力ではなく、準備済みの要約・事実表を渡す例である。生活習慣等の不明事項や指導区分の`null`だけでは入力拒否にしない。`approval.mode == "mock"`を許容するのは明示した実演モードのみとし、実承認と同一視しない。

公開資料パックは別入力であり、このサンプルには含めていない。生成時は詳細設計書第6章に沿って原文・版・ページ・抜粋・適用条件を確認した根拠カードを用意する。資料URLだけや架空の抜粋を根拠にしない。必要なカードがなければ`evidence_insufficient`として該当助言を控える。この3ファイルだけで根拠付き計画案を生成できるという意味ではない。

## サンプルとして具体化した契約

設計書はネスト項目のキー名や列挙値、ハッシュ対象をすべて確定していないため、ここでは`schema_version: step3-input-sample-1.0`として区別する。実装済みスキーマへの適合保証ではなく、実装時の契約検討にも使うサンプルである。

- `approval.status: approved`、`approval.mode: mock`は模擬承認の表現。
- `summary_text`と構造化情報を同じ承認対象に含める。
- `source_rows`は合成の元行をたどるための拡張項目。各`facts[].source_row_id`と値・単位・日付が対応する。LLMに要約させる生データではない。
- `trends[].fact_ids`は比較対象を参照し、`delta`は末尾値から先頭値を引いた計算済み差分。比較不能なら`null`とする。
- `reviewed_findings[].importance: null`は医学的優先順位を提供していないことを表す。
- `guidance_category_unknown_reason`は区分不明の理由を表す拡張項目。
- 注意事項は承認対象の模擬設定として明示し、数値から新規の受診勧奨判定を行っていない。

## ハッシュの照合

トップレベルの`summary_hash`と`approval`を除いたJSON全体を承認対象とする。Pythonの`json.dumps`で`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`を指定し、UTF-8バイト列のSHA-256に`sha256:`を付ける。ファイルのインデントや末尾改行はハッシュに影響しない。

```python
import hashlib
import json
from pathlib import Path

for path in sorted(Path("samples/step3").glob("case_*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = {k: v for k, v in data.items() if k not in ("summary_hash", "approval")}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert data["summary_hash"] == data["approval"]["approved_hash"] == digest
    print(path.name, "hash OK")
```

リポジトリのルートで実行する。内容変更時は要約版を更新し、実演用の模擬レビュー後にハッシュと模擬承認記録を更新する。ハッシュの一致は内容の医学的正しさや実承認を証明しない。
