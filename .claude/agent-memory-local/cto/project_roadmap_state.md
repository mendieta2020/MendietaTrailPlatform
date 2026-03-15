---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-131b (Frontend OrgContext + CoachDashboard + RosterSection, merged 2026-03-15)

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Next PR: PR-132 — Backend: add athlete_id and date range query param filters to WorkoutAssignmentViewSet. This is a PREREQUISITE for PR-131c (frontend AssignmentCalendar).

P1 backend APIs completed (all with tenancy isolation tests):
- Organization, Team, Membership, Coach, Athlete, AthleteCoachAssignment (PR-129 + PR-130)
- WorkoutLibrary, PlannedWorkout (PR-128a)
- WorkoutBlock, WorkoutInterval (PR-128b)
- WorkoutAssignment, WorkoutReconciliation (prior capsule PRs)
- AthleteProfile, RaceEvent, AthleteGoal (PR-115/116)
- Athlete Weekly Adherence (PR-119)
- SessionStatusView with memberships (PR-131a)

P1 frontend completed:
- OrgContext (multi-org switcher) + CoachDashboard + RosterSection (PR-131b)

WorkoutAssignmentViewSet current state:
- Endpoint: GET /api/p1/orgs/<org_id>/assignments/
- Coach: returns ALL assignments in org (no filter params yet)
- Athlete: auto-filtered to own assignments
- Serializer fields: id, athlete_id, planned_workout_id, assigned_by_id, scheduled_date,
  athlete_moved_date, day_order, status, coach_notes, athlete_notes,
  target_zone_override, target_pace_override, target_rpe_override,
  target_power_override, snapshot_version, assigned_at, updated_at, effective_date
- MISSING: planned_workout title nested read (only planned_workout_id returned)
- MISSING: query param filters (?athlete_id=, ?date_from=, ?date_to=)

Test coverage milestones:
- PR-123: 69 tenancy isolation tests for 8 legacy ViewSets
- PR-129: 44 functional tests for 5 Roster ViewSets
- PR-130: 35 tenancy isolation tests for 5 Roster ViewSets
- Total: 935+ tests
