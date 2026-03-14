---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-129 (Coach, Athlete, Team Roster API — 5 ViewSets, 44 tests, merged 2026-03-13)

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Next PR: PR-130 — Tenancy Isolation Test Sweep for P1 Roster ViewSets (same pattern as PR-123 for legacy ViewSets).

P1 CRUD APIs completed:
- Organization, Team, Membership, Coach, Athlete, AthleteCoachAssignment (PR-129)
- WorkoutLibrary, PlannedWorkout (PR-128a)
- WorkoutBlock, WorkoutInterval (PR-128b)
- WorkoutAssignment (prior capsule PRs)

P1 CRUD APIs remaining:
- AthleteProfile, RaceEvent, AthleteGoal ViewSets (if not already built)
- ActivityStream ViewSet (if needed)
- Plan vs Real reconciliation API endpoints

Test coverage milestones:
- PR-123: 69 tenancy isolation tests for 8 legacy ViewSets
- PR-129: 44 functional tests for 5 Roster ViewSets
- PR-130 (next): dedicated tenancy isolation sweep for the 5 Roster ViewSets
