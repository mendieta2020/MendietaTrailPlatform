"""
PR6: Tenant Isolation – ViewSet-level tests using reverse().

Purpose:
- Tenant isolation tests for PlantillaViewSet and VideoUploadViewSet using reverse()
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

import datetime

from django.utils import timezone

from core.models import (
    PlantillaEntrenamiento,
    VideoEjercicio,
    Equipo,
    Alumno,
    Entrenamiento,
    Carrera,
    InscripcionCarrera,
    Pago,
    Actividad,
)

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


# ==============================================================================
#  PR-123: Equipo – Tenant Isolation
# ==============================================================================

class EquipoViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that EquipoViewSet enforces coach-scoped tenant isolation.

    Validated field: Equipo.entrenador (FK to User).
    Scoping mechanism: TenantModelViewSet.get_queryset() → Q(entrenador=user).
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_eq", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_eq", password="pass!")
        self.staff = User.objects.create_user(username="staff_eq", password="pass!", is_staff=True)

        self.equipo_a = Equipo.objects.create(entrenador=self.coach_a, nombre="Equipo A")
        self.equipo_b = Equipo.objects.create(entrenador=self.coach_b, nombre="Equipo B")

    def test_coach_a_list_excludes_coach_b_equipo(self):
        """LIST /api/equipos/ as Coach A → only Coach A's teams."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("equipo-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [e["id"] for e in _results(response)]
        self.assertIn(self.equipo_a.id, ids)
        self.assertNotIn(self.equipo_b.id, ids)

    def test_coach_b_list_excludes_coach_a_equipo(self):
        """LIST /api/equipos/ as Coach B → only Coach B's teams."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("equipo-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [e["id"] for e in _results(response)]
        self.assertIn(self.equipo_b.id, ids)
        self.assertNotIn(self.equipo_a.id, ids)

    def test_coach_a_retrieve_coach_b_equipo_returns_404(self):
        """RETRIEVE Coach B's equipo as Coach A → 404 (not 200, not 403)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("equipo-detail", kwargs={"pk": self.equipo_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_equipo_returns_404(self):
        """RETRIEVE Coach A's equipo as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("equipo-detail", kwargs={"pk": self.equipo_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_equipo(self):
        """PATCH Coach B's equipo as Coach A → 404, data unchanged."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("equipo-detail", kwargs={"pk": self.equipo_b.pk})
        response = self.client.patch(url, {"nombre": "HACKED"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.equipo_b.refresh_from_db()
        self.assertEqual(self.equipo_b.nombre, "Equipo B")

    def test_coach_a_cannot_delete_coach_b_equipo(self):
        """DELETE Coach B's equipo as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("equipo-detail", kwargs={"pk": self.equipo_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Equipo.objects.filter(pk=self.equipo_b.pk).exists())

    def test_staff_list_sees_all_equipos(self):
        """Staff LIST → both coaches' teams visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("equipo-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {e["id"] for e in _results(response)}
        self.assertIn(self.equipo_a.id, ids)
        self.assertIn(self.equipo_b.id, ids)

    def test_staff_retrieve_any_equipo(self):
        """Staff RETRIEVE Coach B's equipo → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("equipo-detail", kwargs={"pk": self.equipo_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.equipo_b.id)


# ==============================================================================
#  PR-123: Alumno – Tenant Isolation
# ==============================================================================

class AlumnoViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that AlumnoViewSet enforces coach-scoped tenant isolation.

    Validated field: Alumno.entrenador (FK to User).
    Scoping mechanism: TenantModelViewSet.get_queryset()
        → Q(entrenador=user) | Q(usuario=user).
    For pure coaches (no perfil_alumno), only Q(entrenador=user) is relevant.
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_al", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_al", password="pass!")
        self.staff = User.objects.create_user(username="staff_al", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno A", email="alumno_a_al@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno B", email="alumno_b_al@test.com"
        )

    def test_coach_a_list_excludes_coach_b_alumno(self):
        """LIST /api/alumnos/ as Coach A → only Coach A's athletes."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("alumno-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [a["id"] for a in _results(response)]
        self.assertIn(self.alumno_a.id, ids)
        self.assertNotIn(self.alumno_b.id, ids)

    def test_coach_b_list_excludes_coach_a_alumno(self):
        """LIST /api/alumnos/ as Coach B → only Coach B's athletes."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("alumno-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [a["id"] for a in _results(response)]
        self.assertIn(self.alumno_b.id, ids)
        self.assertNotIn(self.alumno_a.id, ids)

    def test_coach_a_retrieve_coach_b_alumno_returns_404(self):
        """RETRIEVE Coach B's alumno as Coach A → 404 (not 200, not 403)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("alumno-detail", kwargs={"pk": self.alumno_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_alumno_returns_404(self):
        """RETRIEVE Coach A's alumno as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("alumno-detail", kwargs={"pk": self.alumno_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_alumno(self):
        """PATCH Coach B's alumno as Coach A → 404, data unchanged."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("alumno-detail", kwargs={"pk": self.alumno_b.pk})
        response = self.client.patch(url, {"nombre": "HACKED"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.alumno_b.refresh_from_db()
        self.assertEqual(self.alumno_b.nombre, "Alumno B")

    def test_coach_a_cannot_delete_coach_b_alumno(self):
        """DELETE Coach B's alumno as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("alumno-detail", kwargs={"pk": self.alumno_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Alumno.objects.filter(pk=self.alumno_b.pk).exists())

    def test_staff_list_sees_all_alumnos(self):
        """Staff LIST → both coaches' athletes visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("alumno-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {a["id"] for a in _results(response)}
        self.assertIn(self.alumno_a.id, ids)
        self.assertIn(self.alumno_b.id, ids)

    def test_staff_retrieve_any_alumno(self):
        """Staff RETRIEVE Coach B's alumno → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("alumno-detail", kwargs={"pk": self.alumno_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.alumno_b.id)


# ==============================================================================
#  PR-123: Entrenamiento – Tenant Isolation
# ==============================================================================

class EntrenamientoViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that EntrenamientoViewSet enforces coach-scoped tenant isolation.

    Validated field: Entrenamiento.alumno → Alumno.entrenador (FK chain).
    Scoping mechanism: EntrenamientoViewSet.get_queryset()
        → Q(alumno__entrenador=user) [via both custom and TenantModelViewSet filter].
    Precondition: each coach must have at least one Alumno so that
        user.alumnos.exists() == True and the Q() expression is built.
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_ent", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_ent", password="pass!")
        self.staff = User.objects.create_user(username="staff_ent", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno Ent A", email="alumno_a_ent@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno Ent B", email="alumno_b_ent@test.com"
        )

        self.entrenamiento_a = Entrenamiento.objects.create(
            alumno=self.alumno_a, fecha_asignada=datetime.date.today()
        )
        self.entrenamiento_b = Entrenamiento.objects.create(
            alumno=self.alumno_b, fecha_asignada=datetime.date.today()
        )

    def test_coach_a_list_excludes_coach_b_entrenamiento(self):
        """LIST /api/entrenamientos/ as Coach A → only Coach A's workouts."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("entrenamiento-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [e["id"] for e in _results(response)]
        self.assertIn(self.entrenamiento_a.id, ids)
        self.assertNotIn(self.entrenamiento_b.id, ids)

    def test_coach_b_list_excludes_coach_a_entrenamiento(self):
        """LIST /api/entrenamientos/ as Coach B → only Coach B's workouts."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("entrenamiento-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [e["id"] for e in _results(response)]
        self.assertIn(self.entrenamiento_b.id, ids)
        self.assertNotIn(self.entrenamiento_a.id, ids)

    def test_coach_a_retrieve_coach_b_entrenamiento_returns_404(self):
        """RETRIEVE Coach B's entrenamiento as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("entrenamiento-detail", kwargs={"pk": self.entrenamiento_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_entrenamiento_returns_404(self):
        """RETRIEVE Coach A's entrenamiento as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("entrenamiento-detail", kwargs={"pk": self.entrenamiento_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_entrenamiento(self):
        """PATCH Coach B's entrenamiento as Coach A → 404, record unchanged."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("entrenamiento-detail", kwargs={"pk": self.entrenamiento_b.pk})
        response = self.client.patch(url, {"completado": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.entrenamiento_b.refresh_from_db()
        self.assertFalse(self.entrenamiento_b.completado)

    def test_coach_a_cannot_delete_coach_b_entrenamiento(self):
        """DELETE Coach B's entrenamiento as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("entrenamiento-detail", kwargs={"pk": self.entrenamiento_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Entrenamiento.objects.filter(pk=self.entrenamiento_b.pk).exists())

    def test_staff_list_sees_all_entrenamientos(self):
        """Staff LIST → both coaches' workouts visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("entrenamiento-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {e["id"] for e in _results(response)}
        self.assertIn(self.entrenamiento_a.id, ids)
        self.assertIn(self.entrenamiento_b.id, ids)

    def test_staff_retrieve_any_entrenamiento(self):
        """Staff RETRIEVE Coach B's entrenamiento → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("entrenamiento-detail", kwargs={"pk": self.entrenamiento_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.entrenamiento_b.id)


# ==============================================================================
#  PR-123: Carrera – Fail-Closed Behavior (FINDING-123-A)
# ==============================================================================

class CarreraViewSetFailClosedTests(APITestCase):
    """
    Documents and asserts fail-closed behavior for CarreraViewSet.

    FINDING-123-A: Carrera has no tenant field (no entrenador, alumno, uploaded_by,
    usuario, or equipo). TenantModelViewSet.get_queryset() detects no tenant
    filters and raises PermissionDenied(403) for all non-staff users.

    Consequence: /api/carreras/ is inaccessible to coaches — the endpoint is
    effectively broken for non-staff. This is fail-CLOSED (no cross-tenant leak)
    but also BROKEN for legitimate coach use.

    Action required (PR-124 candidate): Either add an `entrenador` FK to Carrera
    to enable tenant scoping, OR explicitly mark CarreraViewSet as a public
    read-only endpoint (bypassing TenantModelViewSet) if races are meant to be
    shared globally across coaches.

    DO NOT fix production code in this PR.
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_car", password="pass!")
        self.staff = User.objects.create_user(username="staff_car", password="pass!", is_staff=True)

        self.carrera = Carrera.objects.create(
            nombre="Ultra Trail Test",
            fecha=datetime.date.today(),
            distancia_km=42.0,
        )

    def test_coach_cannot_list_carreras_fail_closed(self):
        """LIST /api/carreras/ as coach → 403 (fail-closed: no tenant field on Carrera)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("carrera-list")
        response = self.client.get(url)

        # FINDING-123-A: 403 means fail-closed, not a leak — but the endpoint
        # is broken for legitimate coach use. Fix required in a future PR.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_coach_cannot_retrieve_any_carrera_fail_closed(self):
        """RETRIEVE any carrera as coach → 403 (fail-closed before pk filter)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("carrera-detail", kwargs={"pk": self.carrera.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_list_sees_all_carreras(self):
        """Staff LIST → all carreras visible (staff bypasses tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("carrera-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {c["id"] for c in _results(response)}
        self.assertIn(self.carrera.id, ids)

    def test_staff_retrieve_any_carrera(self):
        """Staff RETRIEVE → 200 (no tenant filter for staff)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("carrera-detail", kwargs={"pk": self.carrera.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.carrera.id)


# ==============================================================================
#  PR-123: InscripcionCarrera – Tenant Isolation
# ==============================================================================

class InscripcionViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that InscripcionViewSet enforces coach-scoped tenant isolation.

    Validated field: InscripcionCarrera.alumno → Alumno.entrenador (FK chain).
    Scoping mechanism: TenantModelViewSet.get_queryset()
        → Q(alumno__entrenador=user).

    Note: Carrera is shared (no tenant field). Isolation is via the alumno owner.
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_ins", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_ins", password="pass!")
        self.staff = User.objects.create_user(username="staff_ins", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno Ins A", email="alumno_a_ins@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno Ins B", email="alumno_b_ins@test.com"
        )

        carrera = Carrera.objects.create(
            nombre="Carrera Inscripcion Test",
            fecha=datetime.date.today(),
            distancia_km=21.0,
        )

        self.inscripcion_a = InscripcionCarrera.objects.create(
            alumno=self.alumno_a, carrera=carrera
        )
        self.inscripcion_b = InscripcionCarrera.objects.create(
            alumno=self.alumno_b, carrera=carrera
        )

    def test_coach_a_list_excludes_coach_b_inscripcion(self):
        """LIST /api/inscripciones/ as Coach A → only Coach A's inscriptions."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("inscripcion-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in _results(response)]
        self.assertIn(self.inscripcion_a.id, ids)
        self.assertNotIn(self.inscripcion_b.id, ids)

    def test_coach_b_list_excludes_coach_a_inscripcion(self):
        """LIST /api/inscripciones/ as Coach B → only Coach B's inscriptions."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("inscripcion-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in _results(response)]
        self.assertIn(self.inscripcion_b.id, ids)
        self.assertNotIn(self.inscripcion_a.id, ids)

    def test_coach_a_retrieve_coach_b_inscripcion_returns_404(self):
        """RETRIEVE Coach B's inscripcion as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("inscripcion-detail", kwargs={"pk": self.inscripcion_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_delete_coach_b_inscripcion(self):
        """DELETE Coach B's inscripcion as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("inscripcion-detail", kwargs={"pk": self.inscripcion_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(InscripcionCarrera.objects.filter(pk=self.inscripcion_b.pk).exists())

    def test_staff_list_sees_all_inscripciones(self):
        """Staff LIST → all inscriptions visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("inscripcion-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {i["id"] for i in _results(response)}
        self.assertIn(self.inscripcion_a.id, ids)
        self.assertIn(self.inscripcion_b.id, ids)

    def test_staff_retrieve_any_inscripcion(self):
        """Staff RETRIEVE Coach B's inscripcion → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("inscripcion-detail", kwargs={"pk": self.inscripcion_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.inscripcion_b.id)


# ==============================================================================
#  PR-123: Pago – Tenant Isolation
# ==============================================================================

class PagoViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that PagoViewSet enforces coach-scoped tenant isolation.

    Validated field: Pago.alumno → Alumno.entrenador (FK chain).
    Scoping mechanism: TenantModelViewSet.get_queryset()
        → Q(alumno__entrenador=user).
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_pago", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_pago", password="pass!")
        self.staff = User.objects.create_user(username="staff_pago", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno Pago A", email="alumno_a_pago@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno Pago B", email="alumno_b_pago@test.com"
        )

        self.pago_a = Pago.objects.create(alumno=self.alumno_a, monto=100.00)
        self.pago_b = Pago.objects.create(alumno=self.alumno_b, monto=200.00)

    def test_coach_a_list_excludes_coach_b_pago(self):
        """LIST /api/pagos/ as Coach A → only Coach A's payments."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("pago-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in _results(response)]
        self.assertIn(self.pago_a.id, ids)
        self.assertNotIn(self.pago_b.id, ids)

    def test_coach_b_list_excludes_coach_a_pago(self):
        """LIST /api/pagos/ as Coach B → only Coach B's payments."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("pago-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in _results(response)]
        self.assertIn(self.pago_b.id, ids)
        self.assertNotIn(self.pago_a.id, ids)

    def test_coach_a_retrieve_coach_b_pago_returns_404(self):
        """RETRIEVE Coach B's pago as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("pago-detail", kwargs={"pk": self.pago_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_pago_returns_404(self):
        """RETRIEVE Coach A's pago as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("pago-detail", kwargs={"pk": self.pago_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_pago(self):
        """PATCH Coach B's pago as Coach A → 404, amount unchanged."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("pago-detail", kwargs={"pk": self.pago_b.pk})
        response = self.client.patch(url, {"monto": "9999.00"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.pago_b.refresh_from_db()
        self.assertEqual(float(self.pago_b.monto), 200.00)

    def test_coach_a_cannot_delete_coach_b_pago(self):
        """DELETE Coach B's pago as Coach A → 404, record persists."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("pago-detail", kwargs={"pk": self.pago_b.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Pago.objects.filter(pk=self.pago_b.pk).exists())

    def test_staff_list_sees_all_pagos(self):
        """Staff LIST → both coaches' payments visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("pago-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {p["id"] for p in _results(response)}
        self.assertIn(self.pago_a.id, ids)
        self.assertIn(self.pago_b.id, ids)

    def test_staff_retrieve_any_pago(self):
        """Staff RETRIEVE Coach B's pago → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("pago-detail", kwargs={"pk": self.pago_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.pago_b.id)


# ==============================================================================
#  PR-123: Actividad – Tenant Isolation
# ==============================================================================

class ActividadViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that ActividadViewSet enforces coach-scoped tenant isolation.

    Validated fields: Actividad.alumno → Alumno.entrenador (FK chain)
                      Actividad.usuario (direct FK to coach who imported).
    Scoping mechanism: TenantModelViewSet.get_queryset()
        → Q(alumno__entrenador=user) | Q(usuario=user).
    Note: ActividadViewSet is read-only (http_method_names = ["get", "head", "options"]).
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_act", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_act", password="pass!")
        self.staff = User.objects.create_user(username="staff_act", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno Act A", email="alumno_a_act@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno Act B", email="alumno_b_act@test.com"
        )

        self.actividad_a = Actividad.objects.create(
            usuario=self.coach_a,
            alumno=self.alumno_a,
            fecha_inicio=timezone.now(),
            source=Actividad.Source.MANUAL,
        )
        self.actividad_b = Actividad.objects.create(
            usuario=self.coach_b,
            alumno=self.alumno_b,
            fecha_inicio=timezone.now(),
            source=Actividad.Source.MANUAL,
        )

    def test_coach_a_list_excludes_coach_b_actividad(self):
        """LIST /api/activities/ as Coach A → only Coach A's activities."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("activities-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [a["id"] for a in _results(response)]
        self.assertIn(self.actividad_a.id, ids)
        self.assertNotIn(self.actividad_b.id, ids)

    def test_coach_b_list_excludes_coach_a_actividad(self):
        """LIST /api/activities/ as Coach B → only Coach B's activities."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("activities-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [a["id"] for a in _results(response)]
        self.assertIn(self.actividad_b.id, ids)
        self.assertNotIn(self.actividad_a.id, ids)

    def test_coach_a_retrieve_coach_b_actividad_returns_404(self):
        """RETRIEVE Coach B's actividad as Coach A → 404 (not 200, not 403)."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("activities-detail", kwargs={"pk": self.actividad_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_b_retrieve_coach_a_actividad_returns_404(self):
        """RETRIEVE Coach A's actividad as Coach B → 404."""
        self.client.force_authenticate(user=self.coach_b)
        url = reverse("activities-detail", kwargs={"pk": self.actividad_a.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_list_sees_all_actividades(self):
        """Staff LIST → both coaches' activities visible (no tenant filter)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("activities-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {a["id"] for a in _results(response)}
        self.assertIn(self.actividad_a.id, ids)
        self.assertIn(self.actividad_b.id, ids)

    def test_staff_retrieve_any_actividad(self):
        """Staff RETRIEVE Coach B's actividad → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("activities-detail", kwargs={"pk": self.actividad_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.actividad_b.id)


# ==============================================================================
#  PR-123: AlumnoPlannedWorkoutViewSet – Tenant Isolation (Nested Route)
# ==============================================================================

class AlumnoPlannedWorkoutViewSetTenantIsolationTests(APITestCase):
    """
    Guarantees that AlumnoPlannedWorkoutViewSet enforces coach-scoped tenant
    isolation on the nested route /api/alumnos/<alumno_id>/planned-workouts/.

    Scoping mechanism: AlumnoPlannedWorkoutViewSet.get_queryset()
        → get_object_or_404(Alumno.filter(entrenador=user), pk=alumno_id).
    Fail-closed: accessing another coach's alumno_id returns 404 before any
    workout data is exposed.
    """

    def setUp(self):
        self.coach_a = User.objects.create_user(username="coach_a_pw", password="pass!")
        self.coach_b = User.objects.create_user(username="coach_b_pw", password="pass!")
        self.staff = User.objects.create_user(username="staff_pw", password="pass!", is_staff=True)

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a, nombre="Alumno PW A", email="alumno_a_pw@test.com"
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b, nombre="Alumno PW B", email="alumno_b_pw@test.com"
        )

        self.entrenamiento_b = Entrenamiento.objects.create(
            alumno=self.alumno_b, fecha_asignada=datetime.date.today()
        )

    def test_coach_a_cannot_list_coach_b_alumno_workouts(self):
        """LIST /api/alumnos/{alumno_b.pk}/planned-workouts/ as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse("alumno-planned-workouts-list", kwargs={"alumno_id": self.alumno_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_retrieve_coach_b_planned_workout(self):
        """RETRIEVE Coach B's workout via Coach B's alumno path as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse(
            "alumno-planned-workouts-detail",
            kwargs={"alumno_id": self.alumno_b.pk, "pk": self.entrenamiento_b.pk},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_planned_workout(self):
        """PATCH Coach B's workout via Coach B's alumno path as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse(
            "alumno-planned-workouts-detail",
            kwargs={"alumno_id": self.alumno_b.pk, "pk": self.entrenamiento_b.pk},
        )
        response = self.client.patch(url, {"completado": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.entrenamiento_b.refresh_from_db()
        self.assertFalse(self.entrenamiento_b.completado)

    def test_coach_a_cannot_delete_coach_b_planned_workout(self):
        """DELETE Coach B's workout via Coach B's alumno path as Coach A → 404."""
        self.client.force_authenticate(user=self.coach_a)
        url = reverse(
            "alumno-planned-workouts-detail",
            kwargs={"alumno_id": self.alumno_b.pk, "pk": self.entrenamiento_b.pk},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Entrenamiento.objects.filter(pk=self.entrenamiento_b.pk).exists())

    def test_staff_can_list_any_alumno_workouts(self):
        """Staff LIST → Coach B's alumno workouts visible (no tenant filter for staff)."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("alumno-planned-workouts-list", kwargs={"alumno_id": self.alumno_b.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [e["id"] for e in _results(response)]
        self.assertIn(self.entrenamiento_b.id, ids)

    def test_staff_can_retrieve_any_planned_workout(self):
        """Staff RETRIEVE Coach B's workout via Coach B's alumno path → 200."""
        self.client.force_authenticate(user=self.staff)
        url = reverse(
            "alumno-planned-workouts-detail",
            kwargs={"alumno_id": self.alumno_b.pk, "pk": self.entrenamiento_b.pk},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.entrenamiento_b.id)
