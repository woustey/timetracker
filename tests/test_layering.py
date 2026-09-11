"""Guard: ``core/`` and ``data/`` import neither PySide6 nor anything from ``ui/``.

PRD-02 §3.1 — this single constraint keeps the duration and rounding logic
testable in milliseconds without a GUI. The check is static (AST), so it also
catches imports hidden inside functions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "timetracker"
GUARDED_PACKAGES = ("core", "data")
FORBIDDEN_PREFIXES = (
    "PySide6",
    "shiboken6",
    "timetracker.ui",
    "timetracker.app",
    "timetracker.services",
    "timetracker.platform",
)


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> list[str]:
    """Absolute module names imported by *path*, relative imports resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _module_name(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                name = f"{base}.{node.module}" if node.module else base
            else:
                name = node.module or ""
            found.append(name)
    return found


def _guarded_files() -> list[Path]:
    return sorted(p for pkg in GUARDED_PACKAGES for p in (SRC / pkg).rglob("*.py"))


def test_guarded_packages_exist() -> None:
    for pkg in GUARDED_PACKAGES:
        assert (SRC / pkg / "__init__.py").is_file(), f"{pkg}/ package missing"


@pytest.mark.parametrize("path", _guarded_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_qt_or_ui_imports(path: Path) -> None:
    offenders = [
        name
        for name in _imports(path)
        if any(name == pre or name.startswith(pre + ".") for pre in FORBIDDEN_PREFIXES)
    ]
    assert not offenders, f"{path.relative_to(SRC)} imports {offenders}"
