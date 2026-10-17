#!/usr/bin/env python3
"""Unified CLI runner for cpp2py-systems-lab.

Inspired by db_lab.py in sql-ra-lab:
- list   : list all modules and labs
- show   : inspect a lab's problem, C++ anchor, and naive translation
- test   : run pytest against solution (default), naive, or reference
- diff   : view diff between naive and solution, or solution and reference
- verify : run meta-verification (assert reference passes and naive fails)
- reset  : reset solution.py back to naive.py
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure root is in sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.loader import LABS_DIR, discover_labs, find_lab  # noqa: E402

_GREEN, _RED, _YELLOW, _CYAN, _DIM, _BOLD, _RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[1m", "\033[0m",
)


def _c(code: str, text: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    return f"{code}{text}{_RESET}"


def cmd_list(args: argparse.Namespace) -> int:
    labs = discover_labs()
    print(_c(_BOLD, "\n═════════════════════════════════════════════════════════════════════════"))
    print(_c(_BOLD, "  cpp2py-systems-lab · Systems Curriculum & Interactive Labs"))
    print(_c(_BOLD, "═════════════════════════════════════════════════════════════════════════\n"))

    current_module = None
    module_names = {
        1: "The CPython Runtime & Memory Model",
        2: "Memory Layout & Core Containers",
        3: "Resource Management & Lifecycles",
        4: "Dynamic Dispatch, Protocols & Type Systems",
        5: "Concurrency Fundamentals & The Python Threading Model",
        6: "Asynchronous I/O & Event-Driven Architecture",
        7: "Serialization & Protocol Buffers",
        8: "Capstone Service: Production-Grade gRPC Microservice",
    }

    for mod_num in range(1, 9):
        mod_labs = [l for l in labs if l.module == mod_num]
        mod_title = module_names.get(mod_num, f"Module {mod_num}")
        print(_c(_CYAN, f"Module {mod_num}: {mod_title}"))
        if not mod_labs:
            print(_c(_DIM, "  (No lab instances generated yet — planned for Stage 2)\n"))
            continue

        for lab in mod_labs:
            sol_exists = (lab.path / "solution.py").exists()
            ref_exists = (lab.path / "_reference.py").exists()
            status = _c(_GREEN, "● Active") if sol_exists else _c(_YELLOW, "○ Template")
            crit_count = len(lab.criteria)
            print(f"  {_c(_BOLD, lab.id):<10} {lab.title:<50} {status}  {_c(_DIM, f'[{crit_count} criteria]')}")
        print()

    print(_c(_DIM, "Run `./lab.py show <LAB_ID>` or `./lab.py test <LAB_ID>` to begin.\n"))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        lab = find_lab(args.lab_id)
    except KeyError as e:
        print(_c(_RED, f"Error: {e}"))
        return 1

    print(_c(_BOLD, f"\n=== {lab.id}: {lab.title} (Module {lab.module}) ==="))
    print(f"Directory: {lab.path.relative_to(ROOT)}\n")

    prob_file = lab.path / "problem.md"
    if prob_file.exists():
        print(_c(_CYAN, "--- Problem Overview ---"))
        print(prob_file.read_text(encoding="utf-8"))

    print(_c(_CYAN, "--- Criteria ---"))
    for c in lab.criteria:
        fail_note = _c(_RED, "[naive must fail]") if c.naive_must_fail else _c(_GREEN, "[parity check]")
        print(f"  {c.id:<4} {_c(_DIM, f'({c.kind})'):<16} {c.description} {fail_note}")
    print()
    return 0


def _get_pytest_executable() -> str:
    venv_pytest = ROOT / ".venv" / "bin" / "pytest"
    if venv_pytest.exists():
        return str(venv_pytest)
    return f"{sys.executable} -m pytest"


def cmd_test(args: argparse.Namespace) -> int:
    try:
        lab = find_lab(args.lab_id)
    except KeyError as e:
        print(_c(_RED, f"Error: {e}"))
        return 1

    target = args.target
    target_file = lab.path / f"{target}.py" if target != "reference" else lab.path / "_reference.py"
    if not target_file.exists():
        if target == "solution":
            # Auto-seed solution from naive if not present
            naive_file = lab.path / "naive.py"
            if naive_file.exists():
                shutil.copy(naive_file, target_file)
                print(_c(_YELLOW, f"Note: Created initial {target_file.name} from naive.py\n"))

    test_file = lab.path / "test_lab.py"
    if not test_file.exists():
        print(_c(_RED, f"Error: Test file {test_file} does not exist."))
        return 1

    pytest_bin = _get_pytest_executable()
    cmd = [pytest_bin, str(test_file), f"--target={target}"]
    if args.verbose:
        cmd.append("-v")
    if args.filter:
        cmd.extend(["-k", args.filter])
    if args.repeat and args.repeat > 1:
        cmd.extend(["--count", str(args.repeat)])

    cmd_str = " ".join(cmd)
    res = subprocess.run(cmd_str, shell=True, cwd=str(ROOT))
    return res.returncode


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        lab = find_lab(args.lab_id)
    except KeyError as e:
        print(_c(_RED, f"Error: {e}"))
        return 1

    if args.with_reference:
        src = lab.path / "solution.py"
        dst = lab.path / "_reference.py"
        from_desc, to_desc = "solution.py", "_reference.py"
    else:
        src = lab.path / "naive.py"
        dst = lab.path / "solution.py"
        from_desc, to_desc = "naive.py", "solution.py"

    if not src.exists() or not dst.exists():
        print(_c(_RED, f"Cannot diff: {src} or {dst} missing."))
        return 1

    lines_src = src.read_text(encoding="utf-8").splitlines(keepends=True)
    lines_dst = dst.read_text(encoding="utf-8").splitlines(keepends=True)

    diff = list(difflib.unified_diff(lines_src, lines_dst, fromfile=from_desc, tofile=to_desc))
    if not diff:
        print(_c(_YELLOW, f"No differences found between {from_desc} and {to_desc}."))
        return 0

    for line in diff:
        if line.startswith("+"):
            print(_c(_GREEN, line), end="")
        elif line.startswith("-"):
            print(_c(_RED, line), end="")
        elif line.startswith("@"):
            print(_c(_CYAN, line), end="")
        else:
            print(line, end="")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        lab = find_lab(args.lab_id)
    except KeyError as e:
        print(_c(_RED, f"Error: {e}"))
        return 1

    print(_c(_BOLD, f"\n=== Meta-Verifying {lab.id}: {lab.title} ==="))
    pytest_bin = _get_pytest_executable()
    test_file = lab.path / "test_lab.py"

    with tempfile.NamedTemporaryFile(suffix=".json") as tmp_ref, tempfile.NamedTemporaryFile(suffix=".json") as tmp_naive:
        # 1. Run reference
        print(_c(_CYAN, "[1/2] Verifying Reference Implementation (_reference.py)..."))
        cmd1 = f"{pytest_bin} {test_file} --target=reference --scorecard-json={tmp_ref.name} -q"
        p1 = subprocess.run(cmd1, shell=True, cwd=str(ROOT), capture_output=True, text=True)

        # 2. Run naive
        print(_c(_CYAN, "[2/2] Verifying Naive Anti-Pattern (naive.py)..."))
        cmd2 = f"{pytest_bin} {test_file} --target=naive --scorecard-json={tmp_naive.name} -q"
        subprocess.run(cmd2, shell=True, cwd=str(ROOT), capture_output=True, text=True)

        # Read JSON reports
        try:
            data_ref = json.loads(Path(tmp_ref.name).read_text(encoding="utf-8"))[lab.id]["criteria"]
            data_naive = json.loads(Path(tmp_naive.name).read_text(encoding="utf-8"))[lab.id]["criteria"]
        except Exception as e:
            print(_c(_RED, f"Error parsing verification scorecard: {e}"))
            print(p1.stderr or p1.stdout)
            return 1

    print(_c(_BOLD, "\nVerification Invariant Check:"))
    all_ok = True

    for c in lab.criteria:
        ref_crit = data_ref.get(c.id, {"passed": 0, "failed": 0})
        naive_crit = data_naive.get(c.id, {"passed": 0, "failed": 0})

        ref_passed = (ref_crit["failed"] == 0 and ref_crit["passed"] > 0)
        naive_failed = (naive_crit["failed"] > 0)

        # Reference must pass
        if not ref_passed:
            print(f"  {_c(_RED, '✘')} {c.id}: Reference FAILED this criterion! Must pass.")
            all_ok = False
            continue

        # If naive_must_fail is True, naive MUST fail
        if c.naive_must_fail:
            if naive_failed:
                print(f"  {_c(_GREEN, '✔')} {c.id}: Reference passed & Naive cleanly caught failing.")
            else:
                print(f"  {_c(_RED, '✘')} {c.id}: Naive PASSED but was expected to fail! Test is not sensitive enough.")
                all_ok = False
        else:
            print(f"  {_c(_GREEN, '✔')} {c.id}: Reference passed & Naive passed parity.")

    if all_ok:
        print(_c(_GREEN, f"\n✔ Lab {lab.id} is verified sound: Reference passes 100% and Naive traps are triggered!"))
        return 0
    else:
        print(_c(_RED, f"\n✘ Lab {lab.id} has invariant violations. Review criteria and test implementations."))
        return 1


def cmd_scaffold(args: argparse.Namespace) -> int:
    mod_num = args.module
    slug = args.slug.lower().replace("-", "_")
    title = args.title
    lab_id = args.id or f"M{mod_num}-L01"

    dest_dir = LABS_DIR / slug
    if dest_dir.exists():
        print(_c(_RED, f"Error: Directory {dest_dir} already exists."))
        return 1

    template_dir = LABS_DIR / "_template"
    if not template_dir.exists():
        print(_c(_RED, f"Error: Template directory {template_dir} missing."))
        return 1

    shutil.copytree(template_dir, dest_dir)

    # Customize lab.toml
    toml_path = dest_dir / "lab.toml"
    content = toml_path.read_text(encoding="utf-8")
    content = content.replace('id = "M_TEMPLATE"', f'id = "{lab_id}"')
    content = content.replace('module = 1', f'module = {mod_num}')
    content = content.replace('title = "Template Lab: Replace With Title"', f'title = "{title}"')
    toml_path.write_text(content, encoding="utf-8")

    # Customize problem.md
    prob_path = dest_dir / "problem.md"
    p_content = prob_path.read_text(encoding="utf-8")
    p_content = p_content.replace("# M_TEMPLATE · Template Lab Title", f"# {lab_id} · {title}")
    prob_path.write_text(p_content, encoding="utf-8")

    print(_c(_GREEN, f"✔ Successfully scaffolded {lab_id} at {dest_dir.relative_to(ROOT)}"))
    print(_c(_DIM, f"Edit {dest_dir}/reference.cpp, naive.py, _reference.py, and test_lab.py to implement."))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    try:
        lab = find_lab(args.lab_id)
    except KeyError as e:
        print(_c(_RED, f"Error: {e}"))
        return 1

    sol = lab.path / "solution.py"
    naive = lab.path / "naive.py"
    if not naive.exists():
        print(_c(_RED, f"Error: {naive} does not exist."))
        return 1

    shutil.copy(naive, sol)
    print(_c(_GREEN, f"Reset {sol.relative_to(ROOT)} to clean naive template."))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CLI harness for cpp2py-systems-lab: interactive C++ to Python systems transition.",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List all modules and labs")

    # show
    p_show = sub.add_parser("show", help="Show details and problem text for a lab")
    p_show.add_argument("lab_id", help="Lab identifier (e.g. M1-L01)")

    # scaffold
    p_scaffold = sub.add_parser("scaffold", help="Scaffold a new Stage 2 lab from template")
    p_scaffold.add_argument("module", type=int, choices=range(1, 9), help="Module number (1-8)")
    p_scaffold.add_argument("slug", help="Lab directory slug (e.g. m3_l01_connection_lifecycle)")
    p_scaffold.add_argument("title", help="Human-readable lab title")
    p_scaffold.add_argument("--id", help="Custom lab ID (defaults to M{module}-L01)")

    # test
    p_test = sub.add_parser("test", help="Run test suite for a lab")
    p_test.add_argument("lab_id", help="Lab identifier (e.g. M1-L01)")
    p_test.add_argument("--target", choices=["solution", "naive", "reference"], default="solution", help="Implementation target")
    p_test.add_argument("-v", "--verbose", action="store_true", help="Verbose pytest output")
    p_test.add_argument("-k", "--filter", help="Test filter expression")
    p_test.add_argument("--repeat", type=int, default=1, help="Repeat tests N times (stress test)")

    # diff
    p_diff = sub.add_parser("diff", help="View diff of code")
    p_diff.add_argument("lab_id", help="Lab identifier (e.g. M1-L01)")
    p_diff.add_argument("--with-reference", action="store_true", help="Diff solution against reference instead of naive")

    # verify
    p_verify = sub.add_parser("verify", help="Meta-verify lab test sensitivity and reference correctness")
    p_verify.add_argument("lab_id", help="Lab identifier (e.g. M1-L01)")

    # reset
    p_reset = sub.add_parser("reset", help="Reset solution.py back to naive.py")
    p_reset.add_argument("lab_id", help="Lab identifier (e.g. M1-L01)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "scaffold": cmd_scaffold,
        "test": cmd_test,
        "diff": cmd_diff,
        "verify": cmd_verify,
        "reset": cmd_reset,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
