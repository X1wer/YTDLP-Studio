"""A forráskód fordítandó szövegeinek kigyűjtése (tr("...") és N_("...") hívások)."""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ytstudio"


def collect() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys.setdefault(node.args[0].value, []).append(f"{path.name}:{node.lineno}")
    return keys


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    found = collect()
    print(json.dumps(sorted(found), ensure_ascii=False, indent=0))
    print(len(found), file=sys.stderr)
