---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-130 (Tenancy Isolation Sweep — Roster ViewSets, 35 tests, merged 2026-03-14)

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Next PR: PR-131 — Frontend Coach Dashboard (first P1 UI connected to real P1 APIs). Requires a prerequisite backend micro-PR (PR-131a) to add org_id + memberships to SessionStatusView response.

P1 backend APIs completed (all with tenancy isolation tests):
- Organization, Team, Membership, Coach, Athlete, AthleteCoachAssignment (PR-129 + PR-130)
- WorkoutLibrary, PlannedWorkout (PR-128a)
- WorkoutBlock, WorkoutInterval (PR-128b)
- WorkoutAssignment, WorkoutReconciliation (prior capsule PRs)
- AthleteProfile, RaceEvent, AthleteGoal (PR-115/116)
- Athlete Weekly Adherence (PR-119)

P1 frontend: no P1 API calls exist yet in frontend. All current pages call legacy /api/ endpoints.

Test coverage milestones:
- PR-123: 69 tenancy isolation tests for 8 legacy ViewSets
- PR-129: 44 functional tests for 5 Roster ViewSets
- PR-130: 35 tenancy isolation tests for 5 Roster ViewSets
- Total: 935+ tests
