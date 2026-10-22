"""The CLI must stay importable on the oldest Typer we declare (0.9), which is what the .deb gets on Ubuntu.

Typer 0.9 raises ``RuntimeError: Type not yet supported: str | None`` for a PEP 604 union in a command
signature, so those use ``Optional[...]``. A regression only shows up on a machine with an old Typer, so
check the source.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _uses_union_operator(node: ast.AST) -> bool:
    return any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(node))


def _is_typer_default(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("Option", "Argument")
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "typer"
    )


def test_no_pep604_union_in_a_typer_parameter():
    tree = ast.parse((ROOT / "stegoforge.py").read_text(encoding="utf-8"))
    offenders = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = fn.args
        positional = args.posonlyargs + args.args
        defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
        for arg, default in [*zip(positional, defaults, strict=True), *zip(args.kwonlyargs, args.kw_defaults, strict=True)]:
            if _is_typer_default(default) and arg.annotation is not None and _uses_union_operator(arg.annotation):
                offenders.append(f"{fn.name}({arg.arg}) line {arg.lineno}")
    assert not offenders, "use Optional[...] for Typer parameters (Typer 0.9 cannot parse `X | None`): " + ", ".join(offenders)
