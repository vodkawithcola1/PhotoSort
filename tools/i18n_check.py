"""Checks the English translation catalog against the source code.

Usage:
    python tools/i18n_check.py [files...]      (default: every file in app/)

Reports:
  * MISSING  – tr("…") / plural form without an English entry
  * PLACEHOLDER – {names} differ between the Polish key and the English text
  * NONLITERAL – tr() called with something other than a plain string literal
  * UNWRAPPED – string literal with Polish letters that is not passed to tr()
    (docstrings, logging calls and lines marked ``# i18n: ignore`` are skipped)
Exit code 1 when anything is reported.
"""
from __future__ import annotations

import ast
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

POLISH_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
PLURAL_FUNCS = {"plural_pl", "count_pl"}
LOG_NAMES = {"log", "logger", "logging", "_log"}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
# modules whose Polish literals are data, not UI text
SKIP_FILES = {"app/i18n/__init__.py", "app/utils/formatting.py", "app/selftest.py"}


def placeholders(text: str) -> set[str]:
    try:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
    except ValueError:
        return {"<invalid>"}


def _func_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_log_call(node: ast.Call) -> bool:
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in LOG_METHODS
            and isinstance(f.value, ast.Name) and f.value.id in LOG_NAMES)


def scan(path: Path):
    """Yield (kind, lineno, text) for keys used and suspicious literals."""
    src = path.read_text("utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    handled: set[int] = set()  # ids of Constant nodes already accounted for

    # docstrings
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                handled.add(id(body[0].value))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node.func)
        if _is_log_call(node) or name in {"getLogger"}:
            for sub in ast.walk(node):
                handled.add(id(sub))
        elif name == "tr" and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                handled.add(id(a))
                yield "KEY", a.lineno, a.value, {k.arg for k in node.keywords if k.arg}
            elif "i18n: ignore" not in lines[node.lineno - 1]:
                yield "NONLITERAL", node.lineno, ast.unparse(a), set()
        elif name in PLURAL_FUNCS:
            for a in node.args[1:]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    handled.add(id(a))
            forms = [a for a in node.args[1:] if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if len(forms) == 3:
                yield "KEY", forms[0].lineno, forms[0].value, None
                yield "KEY", forms[2].lineno, forms[2].value, None

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in handled:
            if POLISH_CHARS & set(node.value):
                line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
                if "i18n: ignore" in line:
                    continue
                if node.end_lineno != node.lineno and len(node.value) > 300:
                    continue  # embedded SQL / stylesheet blobs
                yield "UNWRAPPED", node.lineno, node.value, None


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from app.i18n.en import CATALOG
    files = [Path(a) for a in argv] if argv else sorted((ROOT / "app").rglob("*.py"))
    problems = 0
    for f in files:
        f = f.resolve()
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith("app/i18n/en/"):
            continue
        for kind, line, text, kw in scan(f):
            msg = None
            if kind == "KEY":
                if text not in CATALOG:
                    msg = f"MISSING      {text!r}"
                elif placeholders(text) != placeholders(CATALOG[text]):
                    msg = f"PLACEHOLDER  {text!r} -> {CATALOG[text]!r}"
                elif kw is not None and placeholders(text) - kw:
                    msg = f"PLACEHOLDER  tr() call lacks arguments {sorted(placeholders(text) - kw)} for {text!r}"
            elif kind == "NONLITERAL":
                msg = f"NONLITERAL   tr({text})"
            elif kind == "UNWRAPPED" and rel not in SKIP_FILES:
                msg = f"UNWRAPPED    {text!r}"
            if msg:
                problems += 1
                print(f"{rel}:{line}: {msg}")
    print(f"{problems} problem(s), catalog size {len(CATALOG)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
