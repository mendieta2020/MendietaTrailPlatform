import pytest
from types import SimpleNamespace
from core.compliance import calcular_porcentaje_cumplimiento

class MockEntrenamiento:
    def __init__(self, completado=True, dist_plan=None, dist_real=None, time_plan=None, time_real=None):
        self.completado = completado
        self.distancia_planificada_km = dist_plan
        self.distancia_real_km = dist_real
        self.tiempo_planificado_min = time_plan
        self.tiempo_real_min = time_real

@pytest.mark.unit
def test_compliance_not_completed():
    e = MockEntrenamiento(completado=False, dist_plan=10, dist_real=10)
    assert calcular_porcentaje_cumplimiento(e) == 0

@pytest.mark.unit
def test_compliance_priority_distance():
    # Plan: 10km, Real: 10km (100%)
    # Time Plan: 60, Real: 30 (50%) -> Should ignore time if distance is present
    e = MockEntrenamiento(dist_plan=10, dist_real=10, time_plan=60, time_real=30)
    assert calcular_porcentaje_cumplimiento(e) == 100

@pytest.mark.unit
def test_compliance_time_priority_if_no_distance():
    # Plan Dist: 0/None
    # Plan Time: 60, Real: 60 -> 100%
    e = MockEntrenamiento(dist_plan=None, dist_real=10, time_plan=60, time_real=60)
    assert calcular_porcentaje_cumplimiento(e) == 100

@pytest.mark.unit
def test_compliance_cap_120():
    # Plan: 10km, Real: 20km (200%) -> Should cap at 120
    e = MockEntrenamiento(dist_plan=10, dist_real=20)
    assert calcular_porcentaje_cumplimiento(e) == 120

@pytest.mark.unit
def test_compliance_cap_120_exact():
    # Plan: 10km, Real: 12km (120%) -> Should be 120
    e = MockEntrenamiento(dist_plan=10, dist_real=12)
    assert calcular_porcentaje_cumplimiento(e) == 120

@pytest.mark.unit
def test_compliance_floor_0():
    # Negative real distance? (Shouldn't happen but logic should handle)
    e = MockEntrenamiento(dist_plan=10, dist_real=-5)
    assert calcular_porcentaje_cumplimiento(e) == 0

@pytest.mark.unit
def test_compliance_freestyle():
    # No plan limits -> 100%
    e = MockEntrenamiento(dist_plan=None, time_plan=None)
    assert calcular_porcentaje_cumplimiento(e) == 100

@pytest.mark.unit
def test_compliance_safe_division_zero_plan():
    # Plan dist 0 but not None
    e = MockEntrenamiento(dist_plan=0, time_plan=60, time_real=60)
    # Should fall through to Time
    assert calcular_porcentaje_cumplimiento(e) == 100

@pytest.mark.unit
def test_compliance_mixed_types_decimal_float():
    # Simulating Decimal inputs
    e = MockEntrenamiento(dist_plan=10.0, dist_real=5)
    assert calcular_porcentaje_cumplimiento(e) == 50
