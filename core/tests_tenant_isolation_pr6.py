"""
PR6: Tenant Isolation Tests for Plantillas and Videos

Verifies that Coach A cannot access Coach B's templates or videos.
Fail-closed multi-tenant enforcement.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from core.models import PlantillaEntrenamiento, VideoEjercicio
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()


class PlantillaTenantIsolationTests(APITestCase):
    """Test tenant isolation for PlantillaEntrenamiento (workout templates)."""

    def setUp(self):
        # Create two coaches with separate tenants
        self.coach_a = User.objects.create_user(username="coach_a_pr6", password="pass123")
        self.coach_b = User.objects.create_user(username="coach_b_pr6", password="pass123")
        self.staff_user = User.objects.create_user(username="staff_pr6", password="pass123", is_staff=True)

        # Create plantillas for each coach
        self.plantilla_a = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach_a,
            titulo="Plantilla Coach A",
            deporte="RUN",
            descripcion_global="Template owned by Coach A",
            estructura={"bloques": [{"tipo": "WARMUP", "duracion": 600}]},
            etiqueta_dificultad="MODERATE",
        )
        self.plantilla_b = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach_b,
            titulo="Plantilla Coach B",
            deporte="TRAIL",
            descripcion_global="Template owned by Coach B",
            estructura={"bloques": [{"tipo": "INTERVALS", "duracion": 1200}]},
            etiqueta_dificultad="HARD",
        )

    def test_coach_a_cannot_list_coach_b_plantillas(self):
        """Coach A should only see their own plantillas in list endpoint."""
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.get("/api/plantillas/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Coach A should see exactly 1 plantilla (their own)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.plantilla_a.id)
        self.assertEqual(results[0]["titulo"], "Plantilla Coach A")
        
        # Verify Coach B's plantilla is NOT in the list
        plantilla_ids = [p["id"] for p in results]
        self.assertNotIn(self.plantilla_b.id, plantilla_ids)

    def test_coach_a_cannot_retrieve_coach_b_plantilla(self):
        """Coach A should get 404 when trying to retrieve Coach B's plantilla.
        
        Using 404 instead of 403 to avoid information leakage (fail-closed).
        """
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.get(f"/api/plantillas/{self.plantilla_b.id}/")
        
        # Expect 404 (not found) rather than 403 to avoid info leak
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_update_coach_b_plantilla(self):
        """Coach A should not be able to update Coach B's plantilla."""
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.patch(
            f"/api/plantillas/{self.plantilla_b.id}/",
            {"titulo": "HACKED BY COACH A"},
            format="json"
        )
        
        # Expect 404 (tenant filtering prevents access)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verify plantilla_b was not modified
        self.plantilla_b.refresh_from_db()
        self.assertEqual(self.plantilla_b.titulo, "Plantilla Coach B")

    def test_coach_a_cannot_delete_coach_b_plantilla(self):
        """Coach A should not be able to delete Coach B's plantilla."""
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.delete(f"/api/plantillas/{self.plantilla_b.id}/")
        
        # Expect 404 (tenant filtering prevents access)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verify plantilla_b still exists
        self.assertTrue(PlantillaEntrenamiento.objects.filter(id=self.plantilla_b.id).exists())

    def test_staff_can_access_all_plantillas(self):
        """Staff users should bypass tenant filtering and see all plantillas."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/plantillas/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Staff should see both plantillas
        self.assertEqual(len(results), 2)
        plantilla_ids = {p["id"] for p in results}
        self.assertIn(self.plantilla_a.id, plantilla_ids)
        self.assertIn(self.plantilla_b.id, plantilla_ids)

    def test_coach_b_cannot_list_coach_a_plantillas(self):
        """Reverse check: Coach B should only see their own plantillas."""
        self.client.force_authenticate(user=self.coach_b)
        response = self.client.get("/api/plantillas/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Coach B should see exactly 1 plantilla (their own)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.plantilla_b.id)
        
        # Verify Coach A's plantilla is NOT in the list
        plantilla_ids = [p["id"] for p in results]
        self.assertNotIn(self.plantilla_a.id, plantilla_ids)


class VideoEjercicioTenantIsolationTests(APITestCase):
    """Test tenant isolation for VideoEjercicio (exercise videos)."""

    def setUp(self):
        # Create two coaches with separate tenants
        self.coach_a = User.objects.create_user(username="coach_a_video_pr6", password="pass123")
        self.coach_b = User.objects.create_user(username="coach_b_video_pr6", password="pass123")
        self.staff_user = User.objects.create_user(username="staff_video_pr6", password="pass123", is_staff=True)

        # Create mock video files (simple uploaded files for testing)
        # In real usage, these would be actual video files
        video_file_a = SimpleUploadedFile(
            "video_coach_a.mp4",
            b"fake video content for coach A",
            content_type="video/mp4"
        )
        video_file_b = SimpleUploadedFile(
            "video_coach_b.mp4",
            b"fake video content for coach B",
            content_type="video/mp4"
        )

        # Create videos for each coach
        self.video_a = VideoEjercicio.objects.create(
            titulo="Sentadilla Técnica A",
            archivo=video_file_a,
            uploaded_by=self.coach_a,
        )
        self.video_b = VideoEjercicio.objects.create(
            titulo="Sentadilla Técnica B",
            archivo=video_file_b,
            uploaded_by=self.coach_b,
        )

    def test_coach_a_cannot_list_coach_b_videos(self):
        """Coach A should only see their own videos in list endpoint."""
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.get("/api/upload-video/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Coach A should see exactly 1 video (their own)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.video_a.id)
        self.assertEqual(results[0]["titulo"], "Sentadilla Técnica A")
        
        # Verify Coach B's video is NOT in the list
        video_ids = [v["id"] for v in results]
        self.assertNotIn(self.video_b.id, video_ids)

    def test_coach_a_cannot_retrieve_coach_b_video(self):
        """Coach A should get 404 when trying to retrieve Coach B's video.
        
        Using 404 instead of 403 to avoid information leakage (fail-closed).
        """
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.get(f"/api/upload-video/{self.video_b.id}/")
        
        # Expect 404 (not found) rather than 403 to avoid info leak
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_a_cannot_delete_coach_b_video(self):
        """Coach A should not be able to delete Coach B's video."""
        self.client.force_authenticate(user=self.coach_a)
        response = self.client.delete(f"/api/upload-video/{self.video_b.id}/")
        
        # Expect 404 (tenant filtering prevents access)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verify video_b still exists
        self.assertTrue(VideoEjercicio.objects.filter(id=self.video_b.id).exists())

    def test_staff_can_access_all_videos(self):
        """Staff users should bypass tenant filtering and see all videos."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/upload-video/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Staff should see both videos
        self.assertEqual(len(results), 2)
        video_ids = {v["id"] for v in results}
        self.assertIn(self.video_a.id, video_ids)
        self.assertIn(self.video_b.id, video_ids)

    def test_coach_b_cannot_list_coach_a_videos(self):
        """Reverse check: Coach B should only see their own videos."""
        self.client.force_authenticate(user=self.coach_b)
        response = self.client.get("/api/upload-video/")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        
        # Coach B should see exactly 1 video (their own)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.video_b.id)
        
        # Verify Coach A's video is NOT in the list
        video_ids = [v["id"] for v in results]
        self.assertNotIn(self.video_a.id, video_ids)
