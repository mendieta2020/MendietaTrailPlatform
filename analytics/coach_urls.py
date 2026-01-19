from django.urls import path

from analytics.coach_views import (
    CoachAlertPatchView,
    CoachAthleteAlertsListView,
    CoachAthleteComplianceSummaryView,
    CoachAthletePlanningView,
    CoachAthleteWeekSummaryView,
    CoachGroupWeekSummaryView,
    CoachPlanningDetailView,
)


urlpatterns = [
    path("athletes/<int:athlete_id>/week-summary/", CoachAthleteWeekSummaryView.as_view(), name="coach_athlete_week_summary"),
    path("athletes/<int:athlete_id>/planning/", CoachAthletePlanningView.as_view(), name="coach_athlete_planning"),
    path("planning/<int:planned_id>/", CoachPlanningDetailView.as_view(), name="coach_planning_detail"),
    path("athletes/<int:athlete_id>/compliance/", CoachAthleteComplianceSummaryView.as_view(), name="coach_athlete_compliance"),
    path("groups/<int:group_id>/week-summary/", CoachGroupWeekSummaryView.as_view(), name="coach_group_week_summary"),
    path("athletes/<int:athlete_id>/alerts/", CoachAthleteAlertsListView.as_view(), name="coach_athlete_alerts"),
    path("alerts/<int:alert_id>/", CoachAlertPatchView.as_view(), name="coach_alert_patch"),
]
