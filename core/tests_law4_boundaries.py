"""
Law 4 Guardrail — Provider Boundary Enforcement.

Scans every .py file in core/ at the AST level and fails if any MODULE-LEVEL
'from integrations.' import is found OUTSIDE of documented known shims.

Rationale: Law 4 of CONSTITUTION.md forbids provider logic from leaking into
domain modules.  Module-level imports create hard coupling that breaks the
boundary at import time.  Lazy (function-level) imports are the approved shim
pattern and are NOT flagged by this test.

Approved shim inventory (module-level imports exempted here — do NOT add new
entries without a deliberate architectural decision and CTO sign-off):

  BACKWARD-COMPAT RE-EXPORT BRIDGES (frozen contracts, do not touch):
  - core/strava_activity_normalizer.py  — re-exports integrations.strava.normalizer
  - core/strava_elevation.py            — re-exports integrations.strava.elevation
  - core/strava_mapper.py               — re-exports integrations.strava.mapper
  - core/strava_oauth_views.py          — re-exports integrations.strava.oauth
      (OAuth callback URL is a frozen contract; shim cannot be removed without
       a backward-compatibility migration plan and protective tests.)

  TEST FILES (intentionally import provider code to exercise provider contracts):
  - core/tests_pr14_outbound_delivery_envelope.py

  LAZY FUNCTION-LEVEL IMPORTS (not flagged — approved pattern):
  - core/services.py :: trigger_workout_delivery_if_applicable()
      from integrations.outbound.workout_delivery import queue_workout_delivery
"""

import ast
import os

import pytest

# Resolve core/ directory relative to this test file so the scan always works
# regardless of the working directory pytest is launched from.
CORE_DIR = os.path.dirname(os.path.abspath(__file__))

# Subdirectories to skip (generated or third-party code inside core/).
_SKIP_DIRS = {"__pycache__", ".pytest_cache", "migrations"}

# Known shim files that are deliberately allowed to have module-level
# 'from integrations.' imports.  These represent frozen backward-compat
# contracts or test fixtures.  Every entry must have a justification above.
_KNOWN_SHIM_FILENAMES = {
    "strava_activity_normalizer.py",  # re-export bridge
    "strava_elevation.py",            # re-export bridge
    "strava_mapper.py",               # re-export bridge
    "strava_oauth_views.py",          # frozen OAuth callback shim
    "tests_pr14_outbound_delivery_envelope.py",  # test: exercises provider envelope
}


def _collect_py_files(directory: str):
    """Yield absolute paths for every .py file under *directory* (recursive)."""
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if fname.endswith(".py"):
                yield os.path.join(root, fname)


def _find_module_level_integration_imports(filepath: str) -> list[tuple[int, str]]:
    """
    Return (lineno, import_text) for every module-level 'from integrations.'
    import found in *filepath*.

    Only top-level AST statements (tree.body) are inspected — nested imports
    inside function or class bodies are approved lazy shims and are skipped.
    """
    try:
        with open(filepath, encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    violations: list[tuple[int, str]] = []
    for node in tree.body:  # module-level statements only
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("integrations"):
                names = ", ".join(alias.name for alias in node.names)
                violations.append((node.lineno, f"from {node.module} import {names}"))
    return violations


class TestLaw4ProviderBoundaries:
    """Static-analysis guardrail for Law 4 (CONSTITUTION.md)."""

    def test_no_module_level_integration_imports_in_core(self):
        """
        Every module-level 'from integrations.' import found in core/ is a
        Law 4 violation.  Use lazy (function-level) imports as the approved
        shim pattern instead.
        """
        all_violations: list[str] = []

        for filepath in sorted(_collect_py_files(CORE_DIR)):
            if os.path.basename(filepath) in _KNOWN_SHIM_FILENAMES:
                continue  # documented known shim — exempt
            hits = _find_module_level_integration_imports(filepath)
            for lineno, stmt in hits:
                rel = os.path.relpath(filepath, CORE_DIR)
                all_violations.append(f"  core/{rel}:{lineno}: {stmt}")

        assert not all_violations, (
            "Law 4 violation — module-level 'from integrations.' imports detected in core/.\n"
            "Fix: move the import inside the function that uses it (lazy import).\n"
            "Violations found:\n" + "\n".join(all_violations)
        )
