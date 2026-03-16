---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-131c (Frontend AssignmentCalendar, merged 2026-03-16) + PR-132 (Backend WorkoutAssignment filters, merged 2026-03-15) + fix/auth-members-login (merged 2026-03-16)

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Next PR: PR-133 — Tenancy isolation test sweep for Workout ViewSets (WorkoutLibrary, PlannedWorkout, WorkoutBlock, WorkoutInterval, WorkoutAssignment). Mirrors the PR-130 pattern.

P1 backend APIs completed:
- Organization, Team, Membership, Coach, Athlete, AthleteCoachAssignment (PR-129 + PR-130 tenancy)
- WorkoutLibrary, PlannedWorkout (PR-128a) -- NO tenancy sweep yet
- WorkoutBlock, WorkoutInterval (PR-128b) -- NO tenancy sweep yet
- WorkoutAssignment with filters (PR-132) -- NO tenancy sweep yet
- WorkoutReconciliation (prior capsule PRs) -- NO tenancy sweep yet
- AthleteProfile, RaceEvent, AthleteGoal (PR-115/116) -- NO tenancy sweep yet
- Athlete Weekly Adherence (PR-119)
- SessionStatusView with memberships (PR-131a)

P1 frontend completed:
- OrgContext (multi-org switcher) + CoachDashboard + RosterSection (PR-131b)
- AssignmentCalendar in CoachDashboard (PR-131c)

TENANCY SWEEP DEBT:
- PR-130 covered: CoachViewSet, AthleteRosterViewSet, TeamViewSet, MembershipViewSet, AthleteCoachAssignmentViewSet
- PR-133 target: WorkoutLibraryViewSet, PlannedWorkoutViewSet, WorkoutBlockViewSet, WorkoutIntervalViewSet, WorkoutAssignmentViewSet
- Still pending after PR-133: RaceEventViewSet, AthleteGoalViewSet, AthleteProfileViewSet, ReconciliationViewSet, AthleteAdherenceViewSet

Test coverage milestones:
- PR-123: 69 tenancy isolation tests for 8 legacy ViewSets
- PR-129: 44 functional tests for 5 Roster ViewSets
- PR-130: 35 tenancy isolation tests for 5 Roster ViewSets
- Total: 935+ tests
