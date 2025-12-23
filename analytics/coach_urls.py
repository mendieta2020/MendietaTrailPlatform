from django.urls import path

from analytics.coach_views import (
    CoachAlertPatchView,
    CoachAthleteAlertsListView,
    CoachAthleteWeekSummaryView,
    CoachGroupWeekSummaryView,
)


urlpatterns = [
    path("athletes/<int:athlete_id>/week-summary/", CoachAthleteWeekSummaryView.as_view(), name="coach_athlete_week_summary"),
    path("groups/<int:group_id>/week-summary/", CoachGroupWeekSummaryView.as_view(), name="coach_group_week_summary"),
    path("athletes/<int:athlete_id>/alerts/", CoachAthleteAlertsListView.as_view(), name="coach_athlete_alerts"),
    path("alerts/<int:alert_id>/", CoachAlertPatchView.as_view(), name="coach_alert_patch"),
]

