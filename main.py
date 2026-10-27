import argparse
import json
from pathlib import Path
from health_agent import Gemma, summary, approve, plan, render


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description='健診結果要約・指導計画案（要有識者レビュー）')
    parser.add_argument('step', choices=['summary', 'approve', 'plan'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cards')
    parser.add_argument('--reviewer')
    parser.add_argument('--note')
    args = parser.parse_args()
    output = Path(args.output)
    markdown = output.with_suffix('.md')
    if output == markdown or output.exists() or markdown.exists():
        parser.error('出力は未使用のJSONパスを指定してください（旧版は上書きしません）')
    data = read(args.input)
    try:
        if args.step == 'summary':
            result = summary(data, Gemma())
        elif args.step == 'approve':
            result = approve(data, args.reviewer or '', args.note or '')
        else:
            if not args.cards:
                parser.error('--cards が必要です')
            result = plan(data, read(args.cards), Gemma())
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with markdown.open('x') as f:
        f.write(render(result))


if __name__ == '__main__':
    main()
