import logging
from typing import Any, Dict, List, Optional
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ==============================================================================
#  JSON SCHEMA V1 DEFINITION
# ==============================================================================
# {
#   "schema_version": "1.0",
#   "blocks": [
#     {
#       "type": "WARMUP" | "ACTIVE" | "REST" | "COOLDOWN",
#       "num_reps": int,
#       "steps": [
#         {
#           "duration_type": "TIME" | "DISTANCE" | "LAP_BUTTON" | "CALORIES",
#           "duration_value": float, # seconds or meters
#           "target_type": "HR_ZONE" | "PACE_ZONE" | "POWER_ZONE" | "RPE" | "OPEN",
#           "target_value_min": float,
#           "target_value_max": float,
#           "target_label": str,
#           "description": str
#         }
#       ]
#     }
#   ]
# }

VALID_BLOCK_TYPES = {"WARMUP", "ACTIVE", "REST", "COOLDOWN"}
VALID_DURATION_TYPES = {"TIME", "DISTANCE", "LAP_BUTTON", "CALORIES"}
VALID_TARGET_TYPES = {"HR_ZONE", "PACE_ZONE", "POWER_ZONE", "RPE", "OPEN"}

def validate_schema_v1(data: Dict[str, Any], tolerant: bool = False) -> None:
    """
    Validates that the provided dictionary adheres to the Workout Schema v1.
    
    Args:
        data: The JSON dictionary to validate.
        tolerant: If True, allows empty dicts (for legacy compat).
    
    Raises:
        ValidationError: If the schema is invalid.
    """
    if not data:
        if tolerant:
            return
        raise ValidationError("Workout structure cannot be empty.")

    # Top level check
    if not isinstance(data, dict):
        raise ValidationError("Root structure must be a dictionary.")
    
    # Version check (optional but recommended to be explicit)
    # version = data.get("schema_version")
    # if version and version != "1.0":
    #    logger.warning(f"Validating unknown schema version {version} as v1")

    blocks = data.get("blocks")
    if blocks is None:
        raise ValidationError("Missing 'blocks' array.")
    
    if not isinstance(blocks, list):
        raise ValidationError("'blocks' must be a list.")
    
    for i, block in enumerate(blocks):
        _validate_block(block, i)


def _validate_block(block: Dict[str, Any], index: int) -> None:
    if not isinstance(block, dict):
        raise ValidationError(f"Block {index} must be a dictionary.")
    
    b_type = block.get("type")
    if b_type not in VALID_BLOCK_TYPES:
        raise ValidationError(f"Block {index}: Invalid type '{b_type}'. Allowed: {VALID_BLOCK_TYPES}")
    
    steps = block.get("steps")
    if not isinstance(steps, list):
        raise ValidationError(f"Block {index}: 'steps' must be a list.")
    
    if not steps:
        raise ValidationError(f"Block {index}: must have at least one step.")

    for j, step in enumerate(steps):
        _validate_step(step, index, j)


def _validate_step(step: Dict[str, Any], block_index: int, step_index: int) -> None:
    if not isinstance(step, dict):
        raise ValidationError(f"Block {block_index}, Step {step_index}: Must be a dictionary.")
    
    # Duration
    dur_type = step.get("duration_type")
    if dur_type not in VALID_DURATION_TYPES:
        raise ValidationError(f"Block {block_index}, Step {step_index}: Invalid duration_type '{dur_type}'.")
    
    dur_val = step.get("duration_value")
    if dur_type in {"TIME", "DISTANCE", "CALORIES"}:
        if dur_val is None or not (isinstance(dur_val, (int, float))):
            raise ValidationError(f"Block {block_index}, Step {step_index}: duration_value must be a number for type '{dur_type}'.")
        if dur_val < 0:
            raise ValidationError(f"Block {block_index}, Step {step_index}: duration_value must be positive.")

    # Target
    tgt_type = step.get("target_type")
    if tgt_type and tgt_type not in VALID_TARGET_TYPES:
        raise ValidationError(f"Block {block_index}, Step {step_index}: Invalid target_type '{tgt_type}'.")


def compute_metrics_v1(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes planned metrics (distance, duration, TSS estimate) from the structure.
    Returns:
        {
            "distance_km": float,
            "duration_min": int,
            "tss_estimate": int
        }
    """
    total_seconds = 0.0
    total_meters = 0.0
    total_load = 0.0  # Minimal load Estimate
    
    if not data or not isinstance(data, dict):
        return {"distance_km": 0, "duration_min": 0, "tss_estimate": 0}
        
    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        return {"distance_km": 0, "duration_min": 0, "tss_estimate": 0}

    for block in blocks:
        reps = block.get("num_reps", 1) or 1
        steps = block.get("steps", [])
        
        block_seconds = 0.0
        block_meters = 0.0
        
        for step in steps:
            dur_type = step.get("duration_type")
            dur_val = float(step.get("duration_value") or 0)
            
            # Duration accumulation
            if dur_type == "TIME":
                block_seconds += dur_val
                # Estimate distance? (Assume reasonable pace ex: 5:00/km -> 3.33 m/s)
                # For now, simplistic: 0 distance if time based, unless we want to infer.
                # Let's keep it strictly explicit for V1.
            elif dur_type == "DISTANCE":
                block_meters += dur_val
                # Estimate time? (Assume pace)
                # Let's Estimate 5:00 min/km (3.33 m/s) generic for calculation if missing
                estimated_sec = dur_val / 3.33 
                block_seconds += estimated_sec
            
            # Load Estimation (Very rough RPE based)
            # RPE 1-10. if missing assume 3.
            # TSS ~ (sec * rpe * constant)
            
        total_seconds += (block_seconds * reps)
        total_meters += (block_meters * reps)

    return {
        "distance_km": round(total_meters / 1000.0, 2),
        "duration_min": int(total_seconds / 60),
        "tss_estimate": 0 # Placeholder for V1
    }
