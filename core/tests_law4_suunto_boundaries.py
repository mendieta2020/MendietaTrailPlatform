"""
Law 3 + Law 4 AST Guardrail — Suunto ingestion boundary enforcement.

Scans integrations/suunto/services_suunto_ingest.py at the AST level and
verifies that it does NOT import any Planning models (PlannedWorkout,
WorkoutAssignment, WorkoutBlock, WorkoutInterval).

Rationale (Law 3 — Plan ≠ Real):
  The ingestion service maps provider data to CompletedActivity (Real).
  It must never reference Planning models — even transitively via import —
  to ensure the Plan ≠ Real invariant is structurally enforced, not just
  documented.
"""
from __future__ import annotations

import ast
import os

import pytest

# Resolve integrations/suunto/ relative to this file (core/).
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_CORE_DIR)
_INGEST_FILE = os.path.join(
    _REPO_ROOT, "integrations", "suunto", "services_suunto_ingest.py"
)

# Planning model names that must never appear in the ingestion service.
_FORBIDDEN_NAMES = {"PlannedWorkout", "WorkoutAssignment", "WorkoutBlock", "WorkoutInterval"}


def _collect_imported_names(filepath: str) -> list[tuple[int, str]]:
    """
    Return (lineno, name) for every imported name found anywhere in *filepath*
    (module-level and function-level — any import is a violation here).
    """
    with open(filepath, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=filepath)

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name in _FORBIDDEN_NAMES:
                    hits.append((node.lineno, name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                if name in _FORBIDDEN_NAMES:
                    hits.append((node.lineno, name))
    return hits


class TestLaw3SuuntoIngestionBoundary:
    """Structural guard: services_suunto_ingest.py must not touch Planning models."""

    def test_ingest_service_does_not_import_planning_models(self):
        """
        Law 3 violation if services_suunto_ingest.py imports any of:
        PlannedWorkout, WorkoutAssignment, WorkoutBlock, WorkoutInterval.

        These models represent the Plan side; the ingest service is Real-only.
        """
        assert os.path.isfile(_INGEST_FILE), (
            f"Expected file not found: {_INGEST_FILE}\n"
            "Create integrations/suunto/services_suunto_ingest.py before running this guard."
        )

        violations = _collect_imported_names(_INGEST_FILE)

        assert not violations, (
            "Law 3 violation — services_suunto_ingest.py imports Planning models.\n"
            "The ingestion service must only interact with CompletedActivity (Real).\n"
            "Violations:\n"
            + "\n".join(f"  line {ln}: {name}" for ln, name in violations)
        )
