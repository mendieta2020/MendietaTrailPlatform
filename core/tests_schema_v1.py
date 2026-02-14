from django.test import SimpleTestCase
from django.core.exceptions import ValidationError
from core.schema_v1 import validate_schema_v1, compute_metrics_v1

class SchemaV1Tests(SimpleTestCase):
    def test_validate_valid_schema(self):
        data = {
            "schema_version": "1.0",
            "blocks": [
                {
                    "type": "WARMUP",
                    "steps": [
                        {"duration_type": "TIME", "duration_value": 600, "target_type": "HR_ZONE"}
                    ]
                }
            ]
        }
        # Should not raise
        validate_schema_v1(data)

    def test_validate_invalid_block_type(self):
        data = {
            "blocks": [{"type": "INVALID", "steps": []}]
        }
        with self.assertRaises(ValidationError):
            validate_schema_v1(data)

    def test_validate_missing_blocks(self):
        data = {}
        with self.assertRaises(ValidationError):
            validate_schema_v1(data)
        
        # Tolerant mode
        validate_schema_v1(data, tolerant=True)

    def test_compute_metrics_simple_run(self):
        # 10 min warmup + 2x (1km run + 2 min recover) + 10 min cooldown
        # Total time: 10 + 2*(~5 + 2) + 10 = ~34 min?
        # Let's be precise.
        # Warmup: 600s
        # Active: 2 reps. 
        #   Step 1: 1000m. Est time = 1000/3.33 = 300s.
        #   Step 2: 120s.
        #   Block total: 2 * (300 + 120) = 840s.
        # Cooldown: 600s.
        # Total: 600 + 840 + 600 = 2040s = 34 min.
        # Total dist: 2 * 1000m = 2000m (warmup/cool are time based -> 0 dist in V1 logic? We said explicit.)
        
        data = {
            "blocks": [
                {
                    "type": "WARMUP", 
                    "steps": [{"duration_type": "TIME", "duration_value": 600}]
                },
                {
                    "type": "ACTIVE",
                    "num_reps": 2,
                    "steps": [
                        {"duration_type": "DISTANCE", "duration_value": 1000},
                        {"duration_type": "TIME", "duration_value": 120}
                    ]
                },
                {
                    "type": "COOLDOWN",
                    "steps": [{"duration_type": "TIME", "duration_value": 600}]
                }
            ]
        }
        
        metrics = compute_metrics_v1(data)
        self.assertEqual(metrics["duration_min"], 34)
        self.assertEqual(metrics["distance_km"], 2.0)

    def test_compute_metrics_empty(self):
        metrics = compute_metrics_v1({})
        self.assertEqual(metrics["duration_min"], 0)
        self.assertEqual(metrics["distance_km"], 0)
