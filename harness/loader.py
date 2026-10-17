"""Lab discovery, manifest parsing, and target loading.

A *target* is one of the three implementations of a lab (the triptych):

- ``naive``      — the C-style translation that the tests must reject,
- ``solution``   — the learner's workspace,
- ``reference``  — the idiomatic answer that the tests must accept.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

Target = Literal["solution", "naive", "reference"]

TARGET_FILES: dict[str, str] = {
    "solution": "solution.py",
    "naive": "naive.py",
    "reference": "_reference.py",
}

ROOT = Path(__file__).resolve().parent.parent
LABS_DIR = ROOT / "labs"


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    kind: str
    description: str
    naive_must_fail: bool


@dataclass(frozen=True, slots=True)
class Lab:
    id: str
    module: int
    title: str
    path: Path
    manifest: dict[str, Any]

    @property
    def criteria(self) -> list[Criterion]:
        return [
            Criterion(
                id=c["id"],
                kind=c.get("kind", "correctness"),
                description=c["description"],
                naive_must_fail=bool(c.get("naive_must_fail", False)),
            )
            for c in self.manifest.get("criteria", [])
        ]

    def file(self, role: str) -> Path:
        """Resolve a triptych role ('cpp', 'naive', 'idiomatic') to a path."""
        return self.path / self.manifest["triptych"][role]


def load_manifest(lab_dir: Path) -> dict[str, Any]:
    with (lab_dir / "lab.toml").open("rb") as fh:
        return tomllib.load(fh)


def discover_labs(labs_dir: Path = LABS_DIR) -> list[Lab]:
    labs = []
    for manifest_path in sorted(labs_dir.glob("*/lab.toml")):
        lab_dir = manifest_path.parent
        if lab_dir.name.startswith("_"):
            continue  # _template and other non-lab folders
        m = load_manifest(lab_dir)
        labs.append(Lab(id=m["id"], module=m["module"], title=m["title"], path=lab_dir, manifest=m))
    return labs


def find_lab(lab_id: str, labs_dir: Path = LABS_DIR) -> Lab:
    wanted = lab_id.upper()
    for lab in discover_labs(labs_dir):
        if lab.id.upper() == wanted or lab.path.name == lab_id:
            return lab
    raise KeyError(f"unknown lab {lab_id!r}")


def load_target(lab_dir: Path, target: str) -> ModuleType:
    """Import ``naive.py`` / ``solution.py`` / ``_reference.py`` from a lab folder.

    Each (lab, target) pair gets a unique module name and is registered in
    ``sys.modules`` *before* execution — ``dataclasses`` and ``pickle`` resolve
    classes through ``sys.modules[cls.__module__]``.
    """
    try:
        filename = TARGET_FILES[target]
    except KeyError:
        raise ValueError(f"unknown target {target!r}; expected one of {list(TARGET_FILES)}") from None

    path = lab_dir / filename
    if not path.exists():
        raise FileNotFoundError(path)

    module_name = f"labs.{lab_dir.name}.{target}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
