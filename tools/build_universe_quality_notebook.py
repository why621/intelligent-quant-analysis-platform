"""Build and execute the bounded, offline CR-012 quality companion.

Use Python with the optional notebooks dependencies (nbformat/nbclient/jsonschema/PyYAML).
No live queries or workbook edits. Executed output stays under artifacts.
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


def main():
    root = Path(__file__).resolve().parents[1]
    notebook = nbf.v4.new_notebook()
    notebook.metadata.kernelspec = {
        "display_name": "Python 3", "language": "python", "name": "python3",
    }
    notebook.cells = [
        nbf.v4.new_markdown_cell(
            "# 沪深300名单质量复核（CR-012）\n"
            "## tl;dr\n"
            "已留存的2026-09-07官方名单为300个唯一股票，沪市189、深市111。"
            "只确认当前名单结构与可追溯性，不确认历史成分、一年行情、许可或线上可用性。"
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n"
            "颗粒度：当前快照中的一只成分股票；键为类型/交易所/代码。"
            "依据保存的原文件SHA256、规范化JSON和版本1磁盘契约复核。\n"
            "### Key Assumptions\n"
            "源文件日期不是调样生效日；固定当前池有幸存者偏差。"
            "哈希检测文件与快照是否一致，不是官方数字签名，也不证明数据许可。"
            "XLS列名解析、空值与交易所校验的可运行实现见"
            " services/algorithms/src/quant_platform/data/universe.py。"
        ),
        nbf.v4.new_markdown_cell("## Data\n离线读取本仓库artifacts；不会重新下载、修改源文件或请求股票行情。"),
        nbf.v4.new_code_cell(
            "import hashlib, json\n"
            "from pathlib import Path\n"
            "from collections import Counter\n"
            "from datetime import date, datetime\n"
            "from zoneinfo import ZoneInfo\n"
            "import yaml\n"
            "from jsonschema import Draft202012Validator, FormatChecker\n"
            "root = Path.cwd()\n"
            "while not (root / 'spec.md').is_file():\n"
            "    if root == root.parent: raise RuntimeError('Run inside project')\n"
            "    root = root.parent\n"
            "source = root / 'artifacts/cr012-universe-20260908'\n"
            "document = json.loads((source / 'snapshot.json').read_text(encoding='utf-8'))\n"
            "raw = (source / 'source.xls').read_bytes()\n"
            "schema = yaml.safe_load((root / 'packages/contracts/schemas/universe.yaml').read_text(encoding='utf-8'))['UniverseSnapshot']\n"
            "print({'sourceUrl': document['sourceUrl'], 'sourceDate': document['sourceDate'], 'retrievedAt': document['retrievedAt']})"
        ),
        nbf.v4.new_markdown_cell("## Results\n完整Schema、原始文件哈希、快照哈希、唯一身份、交易所和日期一致性检查。"),
        nbf.v4.new_code_cell(
            "Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)\n"
            "assert hashlib.sha256(raw).hexdigest() == document['sourceSha256']\n"
            "body = {k: v for k, v in document.items() if k != 'snapshotId'}\n"
            "encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')\n"
            "assert hashlib.sha256(encoded).hexdigest() == document['snapshotId']\n"
            "members = document['members']\n"
            "assert len(members) == len({a['symbol'] for a in members}) == len({a['assetId'] for a in members}) == 300\n"
            "for a in members:\n"
            "    assert a['assetId'] == 'stock:' + a['exchange'] + ':' + a['symbol']\n"
            "    assert a['exchange'] == ('SSE' if a['symbol'].startswith('6') else 'SZSE')\n"
            "    assert a['name'].strip()\n"
            "fetched = datetime.fromisoformat(document['retrievedAt']).astimezone(ZoneInfo('Asia/Shanghai')).date()\n"
            "age = (fetched - date.fromisoformat(document['sourceDate'])).days\n"
            "assert 0 <= age <= 7\n"
            "print({'members': len(members), 'uniqueRate': len({a['symbol'] for a in members}) / len(members), 'exchangeCounts': dict(Counter(a['exchange'] for a in members)), 'ageCalendarDaysAtFetch': age, 'snapshotId': document['snapshotId']})"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n"
            "本名单可进入隔离行情验证阶段；没有证据表明已覆盖300只最近一年行情。"
            "此处新鲜度仅相对原下载时间，不表示未来运行时仍是最新名单。"
            "尚无历史快照序列，不能判断调样趋势或历史成员变化。"
            "下一步补逐资产覆盖与独立指数，再推进日频概览、全量回归和云端验收。"
        ),
    ]
    nbf.validate(notebook)
    target = root / "docs/notebooks/cr012-universe-quality.ipynb"
    target.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, target)
    executed = NotebookClient(notebook, timeout=60, kernel_name="python3",
                              resources={"metadata": {"path": str(root)}}).execute()
    output = root / "artifacts/cr012-notebook"
    output.mkdir(parents=True, exist_ok=True)
    nbf.validate(executed)
    nbf.write(executed, output / "executed.ipynb")
    print(f"Notebook executed: {output / 'executed.ipynb'}")
    for cell in executed.cells:
        for result in cell.get("outputs", []):
            if "text" in result:
                print(result["text"])


if __name__ == "__main__":
    main()
