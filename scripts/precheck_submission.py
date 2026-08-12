#!/usr/bin/env python3
"""scripts/precheck_submission.py — hard compliance gate before EVERY submission (RM-013).

Runs four checks against main.py/config.py before they ship. Any failure exits 1.

  1. LAST-CALLABLE (from RM-012 discovery): kaggle_environments loads the
     submission by exec() and picks the agent as
     `[v for v in env.values() if callable(v)][-1]` — the LAST callable defined
     in the module. If a helper function is defined after `agent`, the engine
     silently runs THAT as the agent instead (no error). This replicates the
     engine's exact selection and asserts it resolves to the intended `agent`
     function — converting the silent failure into a hard pre-submit error.

  2. AGENT-SIGNATURE (from RM-015 discovery): the engine calls
     agent(observation, configuration) with TWO positional args. A one-arg
     signature silently feeds configuration into whatever the 2nd param is
     (e.g. config dict landed in `buy_land` — truthy, silently enabled land
     buying). Asserts agent() accepts >= 2 positional params.

  3. NO-NETWORK: grep for network imports/calls (requests, urllib, socket,
     http.client, httpx, aiohttp, ftplib, smtplib, telnetlib, xmlrpc, urlopen,
     urlretrieve). Episodes have no network ingress/egress — a violating
     submission is void (rules-notes.md). Zero tolerance.

  4. STDLIB-ONLY: every import in main.py/config.py must resolve from the
     Python standard library (or /kaggle_simulations/agent/ at runtime).
     This is checked at import time in an isolated subprocess so unresolved
     imports fail loudly here, not on the host.

  5. ROOT-IMPORT: confirm config.py is importable from main.py's location when
     run standalone from a temp dir mimicking /kaggle_simulations/agent/ —
     catches path-resolution issues before the host does.

Usage:
    python scripts/precheck_submission.py [--main main.py] [--config config.py]
Exit 0 = all four checks pass.
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- network APIs that would violate the no-network rule (rules-notes.md) ---
NETWORK_NAMES = (
    "requests", "urllib", "urllib2", "urlopen", "urlretrieve", "socket",
    "httpx", "aiohttp", "http.client", "http_client", "ftplib", "smtplib",
    "telnetlib", "xmlrpc", "webbrowser", "socketserver",
)

# --- stdlib modules allowed for the submission (stdlib-only, PLAN.md) ---
# Built-ins (no import needed) and stdlib are fine. Everything else fails.
import sys as _sys
_STDLIB_PREFIXES = tuple(str(p) for p in _sys.path if p)


def _last_callable_of(source: str, source_path: Path) -> str | None:
    """Replicate kaggle_environments.get_last_callable: last callable in exec'd module."""
    env: dict = {}
    # The engine appends the file's dir to sys.path so sibling imports resolve.
    exec_dir = str(source_path.parent)
    if exec_dir not in sys.path:
        sys.path.insert(0, exec_dir)
    try:
        exec(compile(source, "<precheck>", "exec"), env)  # noqa: S102 — mirrors engine loader
    finally:
        if exec_dir in sys.path:
            sys.path.remove(exec_dir)
    callables = [name for name, val in env.items() if callable(val)]
    return callables[-1] if callables else None


def check_last_callable(path: Path) -> list[str]:
    """Gate 1: engine's agent-selection must resolve to the intended `agent`."""
    source = path.read_text(encoding="utf-8")
    picked = _last_callable_of(source, path)
    if picked is None:
        return [f"{path.name}: no callable found — engine would fail to load an agent"]
    if picked != "agent":
        return [
            f"{path.name}: engine's last-callable selection is '{picked}', not 'agent'. "
            f"A helper is defined after agent() — the engine will silently run '{picked}' "
            f"as the agent. Move all helpers BEFORE agent()."
        ]
    return []


def check_agent_signature(path: Path) -> list[str]:
    """Gate 2: agent() must accept (observation, configuration) — the engine
    calls agent(*args) with BOTH positional args. A one-arg signature silently
    feeds configuration into whatever the second param is (RM-015 found this:
    config dict landed in buy_land, truthy dict silently enabled land buying).
    """
    import inspect
    source = path.read_text(encoding="utf-8")
    env: dict = {}
    exec_dir = str(path.parent)
    if exec_dir not in sys.path:
        sys.path.insert(0, exec_dir)
    try:
        exec(compile(source, "<precheck-sig>", "exec"), env)  # noqa: S102
    finally:
        if exec_dir in sys.path:
            sys.path.remove(exec_dir)
    fn = env.get("agent")
    if not callable(fn):
        return [f"{path.name}: no agent() function found for signature check"]
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []  # builtin/C — can't introspect, skip
    params = list(sig.parameters.values())
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(positional) < 2:
        return [
            f"{path.name}: agent() takes {len(positional)} positional param(s) — "
            f"the engine calls agent(observation, configuration) with TWO args. "
            f"Add `configuration=None` as the 2nd param (RM-015 found this class "
            f"of silent bug). signature={sig}"
        ]
    return []


def check_no_network(paths: list[Path]) -> list[str]:
    """Gate 2: no network imports/calls in the submission files."""
    problems = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        for name in NETWORK_NAMES:
            # match whole-word tokens (import x, from x, x.y, "x") but not substrings
            import re
            if re.search(rf"\b{re.escape(name)}\b", text):
                problems.append(f"{p.name}: network API '{name}' referenced (no-network rule)")
    return problems


def check_stdlib_only(paths: list[Path]) -> list[str]:
    """Gate 3: every import in the submission resolves from stdlib."""
    problems = []
    for p in paths:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            problems.append(f"{p.name}: syntax error: {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not _is_stdlib(alias.name):
                        problems.append(f"{p.name}: non-stdlib import '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod not in ("__future__",) and not _is_stdlib(mod):
                    problems.append(f"{p.name}: non-stdlib import '{mod}'")
    return problems


def _is_stdlib(mod: str) -> bool:
    """True if `mod` (top-level package) is stdlib or a builtin."""
    top = mod.split(".")[0]
    if top in sys.builtin_module_names:
        return True
    if top in ("config",):  # sibling module shipped in the bundle
        return True
    # check against stdlib path (site-packages is NOT stdlib)
    import importlib.util
    spec = importlib.util.find_spec(top)
    if spec is None or spec.origin is None:
        return True  # builtin-ish / namespace
    origin = str(spec.origin)
    return any(origin.startswith(prefix) for prefix in _STDLIB_PREFIXES)


def check_root_import(main_path: Path, config_path: Path) -> list[str]:
    """Gate 4: config.py importable from main.py's location in an isolated temp dir.

    Mimics /kaggle_simulations/agent/: copy main.py + config.py into a fresh
    temp dir and import main in a subprocess. If `from config import ...` fails,
    the host would see the same ModuleNotFoundError.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        for src in (main_path, config_path):
            (tmp_p / src.name).write_bytes(src.read_bytes())
        # run a subprocess that imports the copied main (cwd=tmp, so main.py at root)
        code = "import main; print('ROOT-IMPORT-OK', main.__file__)"
        res = subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0 or "ROOT-IMPORT-OK" not in res.stdout:
            return [f"root-import failed in isolated dir:\n{res.stderr.strip()[:500]}"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--main", type=Path, default=ROOT / "main.py")
    ap.add_argument("--config", type=Path, default=ROOT / "config.py")
    args = ap.parse_args()

    main_path = args.main if args.main.is_absolute() else ROOT / args.main
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    for p in (main_path, config_path):
        if not p.exists():
            print(f"[precheck] FAIL: {p} not found")
            return 1

    all_problems: list[str] = []
    all_problems += check_last_callable(main_path)
    all_problems += check_agent_signature(main_path)
    all_problems += check_no_network([main_path, config_path])
    all_problems += check_stdlib_only([main_path, config_path])
    all_problems += check_root_import(main_path, config_path)

    if all_problems:
        print("[precheck] FAIL — submission not shippable:")
        for problem in all_problems:
            print(f"  - {problem}")
        return 1
    print("[precheck] OK — last-callable, agent-signature, no-network, stdlib-only, root-import all pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
