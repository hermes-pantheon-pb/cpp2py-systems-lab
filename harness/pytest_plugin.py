"""pytest plugin: target selection, the ``impl`` fixture, and the criteria scorecard."""

from __future__ import annotations

import json
import os
import platform
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType

import pytest

from .loader import TARGET_FILES, Lab, load_manifest, load_target
from .probes import is_free_threaded

_GREEN, _RED, _YELLOW, _DIM, _BOLD, _RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("cpp2py-lab")
    group.addoption(
        "--target",
        choices=sorted(TARGET_FILES),
        default=os.environ.get("LAB_TARGET", "solution"),
        help="Which implementation to verify (default: solution, or $LAB_TARGET).",
    )
    group.addoption(
        "--scorecard-json",
        default=None,
        metavar="PATH",
        help="Write per-criterion outcomes as JSON (used by `lab.py verify`).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "criterion(id): link a test to a lab.toml criterion")
    config.addinivalue_line("markers", "slow: long-running stress or benchmark test")
    config.pluginmanager.register(ScorecardPlugin(config), "cpp2py-scorecard")


def pytest_report_header(config: pytest.Config) -> str:
    gil = "DISABLED (free-threaded)" if is_free_threaded() else "enabled"
    return (
        f"cpp2py-lab: target={config.getoption('--target')} | "
        f"{platform.python_implementation()} {platform.python_version()} | GIL {gil}"
    )


@pytest.fixture(scope="module")
def impl(request: pytest.FixtureRequest) -> ModuleType:
    """The module under test (naive, solution, or reference) for this lab."""
    lab_dir = Path(request.module.__file__).resolve().parent
    target = request.config.getoption("--target")
    try:
        return load_target(lab_dir, target)
    except FileNotFoundError as exc:
        pytest.fail(f"target file missing: {exc}", pytrace=False)


class ScorecardPlugin:
    """Groups test outcomes by ``@pytest.mark.criterion`` and prints a scorecard."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.meta: dict[str, tuple[Path, str]] = {}  # nodeid -> (lab_dir, criterion)
        self.outcomes: dict[str, str] = {}  # nodeid -> passed | failed | skipped

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        for item in items:
            marker = item.get_closest_marker("criterion")
            crit = str(marker.args[0]) if marker and marker.args else "—"
            self.meta[item.nodeid] = (Path(item.path).resolve().parent, crit)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.failed:
            self.outcomes[report.nodeid] = "failed"
        elif report.skipped:
            self.outcomes.setdefault(report.nodeid, "skipped")
        elif report.when == "call":
            self.outcomes.setdefault(report.nodeid, "passed")

    def _aggregate(self) -> dict[Path, dict[str, dict[str, int]]]:
        agg: dict[Path, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
        )
        for nodeid, (lab_dir, crit) in self.meta.items():
            outcome = self.outcomes.get(nodeid)
            if outcome:
                agg[lab_dir][crit][outcome] += 1
        return agg

    def pytest_terminal_summary(self, terminalreporter, exitstatus: int) -> None:  # noqa: ANN001
        agg = self._aggregate()
        if not agg:
            return
        color = terminalreporter.isatty and not os.environ.get("NO_COLOR")
        c = (lambda code, s: f"{code}{s}{_RESET}") if color else (lambda code, s: s)
        target = self.config.getoption("--target")
        payload: dict[str, dict[str, object]] = {}

        terminalreporter.write_sep("━", "criteria scorecard")
        for lab_dir, crits in sorted(agg.items()):
            manifest = load_manifest(lab_dir)
            lab = Lab(manifest["id"], manifest["module"], manifest["title"], lab_dir, manifest)
            described = {cr.id: cr for cr in lab.criteria}
            terminalreporter.write_line(
                c(_BOLD, f"{lab.id} · {lab.title}") + c(_DIM, f"   [target={target}]")
            )
            lab_payload: dict[str, object] = {}
            for crit_id in sorted(crits):
                counts = crits[crit_id]
                total = counts["passed"] + counts["failed"]
                if counts["failed"]:
                    mark = c(_RED, "✘")
                elif counts["passed"]:
                    mark = c(_GREEN, "✔")
                else:
                    mark = c(_YELLOW, "∅")
                cr = described.get(crit_id)
                kind = f"{cr.kind:<12}" if cr else " " * 12
                desc = cr.description if cr else "(untagged tests)"
                terminalreporter.write_line(
                    f"  {mark} {crit_id:<4} {c(_DIM, kind)} {desc}  "
                    + c(_DIM, f"{counts['passed']}/{total}")
                )
                lab_payload[crit_id] = dict(counts)
            payload[lab.id] = {"target": target, "criteria": lab_payload}

        path = self.config.getoption("--scorecard-json")
        if path:
            Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


# Re-exported for conftest.py convenience.
__all__ = ["ScorecardPlugin", "impl", "pytest_addoption", "pytest_configure", "pytest_report_header"]

if sys.version_info < (3, 12):  # pragma: no cover
    raise RuntimeError("cpp2py-systems-lab requires Python 3.12+")
