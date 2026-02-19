"""
PR6: Tenant Isolation – ViewSet-level tests using reverse().

Purpose:
- Mirror isolation guarantees from tests_tenant_isolation_pr6.py.
- Use Django reverse() to validate router basenames explicitly.
- Covers PlantillaViewSet (basename='plantilla') and
  VideoUploadViewSet (basename='upload-video').
- Fail-closed: cross-tenant access must return 404, never 200.

Router basenames (from core/urls.py):
  router.register(r'plantillas', PlantillaViewSet, basename='plantilla')
  router.register(r'upload-video', VideoUploadViewSet, basename='upload-video')
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import PlantillaEntrenamiento, VideoEjercicio

User = get_user_model()


def _results(response):
    """Normalize paginated vs. non-paginated list responses."""
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


# ==============================================================================
#  PlantillaEntrenamiento – Tenant Isolation
# ==============================================================================

class PlantillaViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that PlantillaViewSet enforces coach-scoped tenant isolation.

    Validated field: PlantillaEntrenamiento.entrenador (FK to User).
    Scoping mechanism: PlantillaViewSet.get_queryset() → filter(entrenador=user).
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(
            username="coach_a_vst", password="pass!"
        )
        self.coach_b = User.objects.create_user(
            username="coach_b_vst", password="pass!"
        )
        self.staff = User.objects.create_user(
            username="staff_vst", password="pass!", is_staff=True
        )

        self.plantilla_a = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach_a,
            titulo="Plantilla A (coach_a)",
            deporte="RUN",
            descripcion_global="Owned by coach_a",
            etiqueta_dificultad="EASY",
        )
        self.plantilla_b = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach_b,
            titulo="Plantilla B (coach_b)",
            deporte="TRAIL",
            descripcion_global="Owned by coach_b",
            etiqueta_dificultad="HARD",
        )

    # ------------------------------------------------------------------
    # LIST isolation
    # ------------------------------------------------------------------

    def test_coach_a_list_does_not_include_coach_b_plantilla(self):
        """LIST /api/plantillas/ as Coach A → only Coach A's template."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("plantilla-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in _results(response)]

        self.assertIn(self.plantilla_a.id, ids)
        self.assertNotIn(self.plantilla_b.id, ids)

    def test_coach_b_list_does_not_include_coach_a_plantilla(self):
        """LIST /api/plantillas/ as Coach B → only Coach B's template."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("plantilla-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in _results(response)]

        self.assertIn(self.plantilla_b.id, ids)
        self.assertNotIn(self.plantilla_a.id, ids)

    # ------------------------------------------------------------------
    # RETRIEVE isolation (fail-closed: 404, not 403)
    # ------------------------------------------------------------------

    def test_coach_a_retrieve_coach_b_plantilla_returns_404(self):
        """RETRIEVE Coach B's plantilla as Coach A → 404 (not 200, not 403)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("plantilla-detail", kwargs={"pk": self.plantilla_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_plantilla_returns_404(self):
        """RETRIEVE Coach A's plantilla as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("plantilla-detail", kwargs={"pk": self.plantilla_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # UPDATE isolation
    # ------------------------------------------------------------------

    def test_coach_a_cannot_update_coach_b_plantilla(self):
        """PATCH Coach B's plantilla as Coach A → 404, data unchanged."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("plantilla-detail", kwargs={"pk": self.plantilla_b.pk})
        response = self.client.patch(
            url, {"titulo": "HACKED"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.plantilla_b.refresh_from_db()
        self.assertEqual(self.plantilla_b.titulo, "Plantilla B (coach_b)")

    # ------------------------------------------------------------------
    # DELETE isolation
    # ------------------------------------------------------------------

    def test_coach_a_cannot_delete_coach_b_plantilla(self):
        """DELETE Coach B's plantilla as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("plantilla-detail", kwargs={"pk": self.plantilla_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            PlantillaEntrenamiento.objects.filter(pk=self.plantilla_b.pk).exists()
        )

    # ------------------------------------------------------------------
    # Staff bypass
    # ------------------------------------------------------------------

    def test_staff_list_sees_all_plantillas(self):
        """Staff LIST → both coaches' templates visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("plantilla-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {p["id"] for p in _results(response)}

        self.assertIn(self.plantilla_a.id, ids)
        self.assertIn(self.plantilla_b.id, ids)

    def test_staff_retrieve_any_plantilla(self):
        """Staff RETRIEVE Coach B's plantilla → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("plantilla-detail", kwargs={"pk": self.plantilla_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.plantilla_b.id)


# ==============================================================================
#  VideoEjercicio – Tenant Isolation
# ==============================================================================

class VideoUploadViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that VideoUploadViewSet enforces coach-scoped tenant isolation.

    Validated field: VideoEjercicio.uploaded_by (FK to User).
    Scoping mechanism: TenantModelViewSet.get_queryset() → Q(uploaded_by=user).
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(
            username="coach_a_vid_vst", password="pass!"
        )
        self.coach_b = User.objects.create_user(
            username="coach_b_vid_vst", password="pass!"
        )
        self.staff = User.objects.create_user(
            username="staff_vid_vst", password="pass!", is_staff=True
        )

        self.video_a = VideoEjercicio.objects.create(
            titulo="Sentadilla A",
            archivo=SimpleUploadedFile(
                "vid_a.mp4", b"fake-video-a", content_type="video/mp4"
            ),
            uploaded_by=self.coach_a,
        )
        self.video_b = VideoEjercicio.objects.create(
            titulo="Sentadilla B",
            archivo=SimpleUploadedFile(
                "vid_b.mp4", b"fake-video-b", content_type="video/mp4"
            ),
            uploaded_by=self.coach_b,
        )

    # ------------------------------------------------------------------
    # LIST isolation
    # ------------------------------------------------------------------

    def test_coach_a_list_does_not_include_coach_b_video(self):
        """LIST /api/upload-video/ as Coach A → only own video."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("upload-video-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in _results(response)]

        self.assertIn(self.video_a.id, ids)
        self.assertNotIn(self.video_b.id, ids)

    def test_coach_b_list_does_not_include_coach_a_video(self):
        """LIST /api/upload-video/ as Coach B → only own video."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("upload-video-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in _results(response)]

        self.assertIn(self.video_b.id, ids)
        self.assertNotIn(self.video_a.id, ids)

    # ------------------------------------------------------------------
    # RETRIEVE isolation (fail-closed: 404, not 403)
    # ------------------------------------------------------------------

    def test_coach_a_retrieve_coach_b_video_returns_404(self):
        """RETRIEVE Coach B's video as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("upload-video-detail", kwargs={"pk": self.video_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_video_returns_404(self):
        """RETRIEVE Coach A's video as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("upload-video-detail", kwargs={"pk": self.video_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # DELETE isolation
    # ------------------------------------------------------------------

    def test_coach_a_cannot_delete_coach_b_video(self):
        """DELETE Coach B's video as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("upload-video-detail", kwargs={"pk": self.video_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            VideoEjercicio.objects.filter(pk=self.video_b.pk).exists()
        )

    # ------------------------------------------------------------------
    # Staff bypass
    # ------------------------------------------------------------------

    def test_staff_list_sees_all_videos(self):
        """Staff LIST → both coaches' videos visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("upload-video-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {v["id"] for v in _results(response)}

        self.assertIn(self.video_a.id, ids)
        self.assertIn(self.video_b.id, ids)

    def test_staff_retrieve_any_video(self):
        """Staff RETRIEVE Coach B's video → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("upload-video-detail", kwargs={"pk": self.video_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.video_b.id)
