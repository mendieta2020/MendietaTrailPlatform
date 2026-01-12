from django.test import SimpleTestCase

from backend.celery import app


class CeleryRoutingTests(SimpleTestCase):
    def assert_task_queue(self, task_name: str, expected_queue: str) -> None:
        route = app.amqp.router.route({}, task_name)
        queue = route.get("queue")
        queue_name = queue.name if hasattr(queue, "name") else queue
        self.assertEqual(queue_name, expected_queue)

    def test_routes_strava_ingest_tasks(self) -> None:
        self.assert_task_queue("strava.process_event", "strava_ingest")
        self.assert_task_queue("strava.backfill_activities", "strava_ingest")
        self.assert_task_queue("strava.drain_events_for_athlete", "strava_ingest")

    def test_routes_analytics_tasks(self) -> None:
        self.assert_task_queue("analytics.recompute_injury_risk_daily", "analytics_recompute")
        self.assert_task_queue("analytics.recompute_pmc_from_activities", "analytics_recompute")
        self.assert_task_queue("analytics.reclassify_activities_for_alumno", "analytics_recompute")

    def test_routes_notifications_tasks(self) -> None:
        self.assert_task_queue("notifications.send_email", "notifications")
