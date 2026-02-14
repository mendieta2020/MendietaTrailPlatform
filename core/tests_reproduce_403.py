from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import Alumno, Equipo
from analytics.models import DailyActivityAgg

User = get_user_model()

class HybridCoach403ReproductionTests(TestCase):
    """
    Reproduces the issue where a Coach who also has a 'perfil_alumno' (Hybrid User)
    gets 403 Forbidden on coach endpoints like /api/coach/athletes/{id}/week-summary/.
    """
    def setUp(self):
        self.client = APIClient()
        
        # 1. Create a User who will be the Coach
        self.coach_user = User.objects.create_user(username="coach_hybrid", password="pass")
        
        # 2. Assign this user as 'entrenador' of an athlete
        self.athlete_user = User.objects.create_user(username="athlete_client", password="pass")
        self.athlete = Alumno.objects.create(
            entrenador=self.coach_user,
            usuario=self.athlete_user,
            nombre="Client",
            apellido="Athlete",
            email="client@test.com"
        )
        
        # 3. CRITICAL: Give the Coach User a 'perfil_alumno' (Hybrid)
        # This makes hasattr(self.coach_user, 'perfil_alumno') True.
        # In the current system, this triggers IsCoachUser -> False ==> 403.
        self.coach_as_athlete = Alumno.objects.create(
            entrenador=None, # Self-coached or whatever
            usuario=self.coach_user,
            nombre="Hybrid",
            apellido="Coach",
            email="hybrid@test.com"
        )
        
        # 4. Create a Pure Athlete User (has profile, but NO students)
        self.pure_athlete_user = User.objects.create_user(username="pure_athlete", password="pass")
        self.pure_athlete = Alumno.objects.create(
            entrenador=None,
            usuario=self.pure_athlete_user,
            nombre="Pure",
            apellido="Athlete",
            email="pure@test.com"
        )

        
        # Data setup for week-summary
        today = date.today()
        year, week, _ = today.isocalendar()
        self.week_param = f"{year}-{week:02d}"
        
        DailyActivityAgg.objects.create(
            alumno=self.athlete,
            fecha=today,
            sport=DailyActivityAgg.Sport.RUN,
            load=10,
            duration_s=600,
            distance_m=1000,
            calories_kcal=100
        )

    def test_hybrid_coach_accessing_own_athlete_week_summary(self):
        """
        Expectation: 200 OK (Coach accessing their student).
        Actual Bug: 403 Forbidden (because Coach has 'perfil_alumno').
        """
        self.client.force_authenticate(user=self.coach_user)
        path = f"/api/coach/athletes/{self.athlete.id}/week-summary/?week={self.week_param}"
        print(f"\nRequesting {path} as Hybrid Coach...")
        
        res = self.client.get(path)
        
        print(f"Status Code: {res.status_code}")
        
        self.assertEqual(res.status_code, 200, "Hybrid coach should be able to access their athlete's data")
        self.assertEqual(res.data["athlete_id"], self.athlete.id)

    def test_pure_athlete_accessing_any_week_summary_is_forbidden(self):
        """
        Expectation: 403 Forbidden.
        Reason: Pure athlete user (IsCoachUser=False) should not access /api/coach/
        even if they request their own data (because we want strict role separation).
        """
        self.client.force_authenticate(user=self.pure_athlete_user)
        # Trying to access their OWN week summary via coach API
        path = f"/api/coach/athletes/{self.pure_athlete.id}/week-summary/?week={self.week_param}"
        print(f"\nRequesting {path} as Pure Athlete...")
        
        res = self.client.get(path)
        print(f"Status Code: {res.status_code}")
        
        # Should be 403 because IsCoachUser checks 'user.alumnos.exists()' which is False for pure athlete
        self.assertEqual(res.status_code, 403, "Pure athlete should get 403 on coach endpoint")

    def test_hybrid_coach_accessing_self_via_coach_api_is_404(self):
        """
        Expectation: 404 Not Found (or 403).
        Reason: Even though Hybrid Coach is a Coach, the 'require_athlete_for_coach' strict resolver
        checks 'entrenador=user'.
        If the Hybrid Coach is NOT their own trainer (entrenador=None in setup), they cannot see themselves.
        """
        self.client.force_authenticate(user=self.coach_user)
        path = f"/api/coach/athletes/{self.coach_as_athlete.id}/week-summary/?week={self.week_param}"
        print(f"\nRequesting SELF {path} as Hybrid Coach...")
        
        res = self.client.get(path)
        print(f"Status Code: {res.status_code}")
        
        # Should be 404 because require_athlete_for_coach raises NotFound if not found in queryset
        self.assertEqual(res.status_code, 404, "Hybrid coach accessing self (not student) should be 404")
