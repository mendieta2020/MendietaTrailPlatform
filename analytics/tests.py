from django.test import TestCase

from analytics.injury_risk import compute_injury_risk


class ComputeInjuryRiskTests(TestCase):
    def test_base_risk_by_tsb(self):
        r1 = compute_injury_risk(ctl=50, atl=80, tsb=-40)
        self.assertEqual(r1.risk_level, "HIGH")
        self.assertGreaterEqual(r1.risk_score, 80)

        r2 = compute_injury_risk(ctl=50, atl=70, tsb=-20)
        self.assertEqual(r2.risk_level, "MEDIUM")

        r3 = compute_injury_risk(ctl=50, atl=55, tsb=-5)
        self.assertEqual(r3.risk_level, "LOW")

    def test_atl_growth_escalates_one_level(self):
        # Base LOW -> escalates to MEDIUM
        r = compute_injury_risk(ctl=50, atl=60, tsb=-5, atl_7d_ago=40)
        self.assertEqual(r.risk_level, "MEDIUM")
        self.assertIn("ATL creció >20% en 7 días", r.risk_reasons)

    def test_consecutive_high_load_escalates_one_level(self):
        # Base MEDIUM -> escalates to HIGH
        r = compute_injury_risk(
            ctl=50,
            atl=70,
            tsb=-20,
            last_3_days_tss=[120, 130, 125],
            high_tss_threshold=100,
            high_load_relative_to_ctl=1.5,
        )
        self.assertEqual(r.risk_level, "HIGH")
        self.assertTrue(any("3+ días consecutivos" in s for s in r.risk_reasons))
