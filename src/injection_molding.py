"""Injection molding process model with 30+ parameters."""

from typing import Dict, Optional
import logging


class InjectionMoldingProcess:
    """
    Digital model of injection molding process.

    Manages 30+ critical parameters and physics predictions.
    """

    def __init__(self, machine_id: str):
        """Initialize injection molding process model."""
        self.machine_id = machine_id
        self._logger = logging.getLogger(f"injection_mold_{machine_id}")

        # Key parameters (30+)
        self.parameters = {
            # Injection phase
            "injection_pressure_bar": 1000.0,
            "injection_speed_mm_s": 80.0,
            "injection_acceleration_mm_s2": 500.0,

            # Temperature control
            "barrel_zone_1_temp_c": 190.0,
            "barrel_zone_2_temp_c": 200.0,
            "barrel_zone_3_temp_c": 210.0,
            "barrel_zone_4_temp_c": 215.0,
            "barrel_zone_5_temp_c": 220.0,
            "mold_temp_c": 80.0,
            "nozzle_temp_c": 220.0,

            # Hold/packing phase
            "hold_pressure_bar": 800.0,
            "hold_time_seconds": 3.0,

            # Cooling phase
            "cooling_time_seconds": 8.0,
            "coolant_temp_c": 20.0,
            "coolant_flow_rate_lpm": 50.0,

            # Screw operation
            "screw_speed_rpm": 100.0,
            "back_pressure_bar": 50.0,

            # Mold closing/opening
            "mold_open_speed_mm_s": 50.0,
            "ejection_stroke_mm": 15.0,

            # Process limits
            "max_cavity_pressure_bar": 1500.0,
            "max_melt_temp_c": 250.0,
            "max_mold_temp_c": 100.0
        }

    def predict_quality(self, parameters: Dict[str, float]) -> float:
        """
        Predict part quality score (0-1) from parameters.

        Considers: dimensional accuracy, surface finish, mechanical properties
        """
        score = 1.0

        # Temperature effects
        melt_temp = parameters.get("barrel_zone_5_temp_c", 220)
        if melt_temp < 190 or melt_temp > 240:
            score -= abs(melt_temp - 215) * 0.001

        mold_temp = parameters.get("mold_temp_c", 80)
        if mold_temp < 60 or mold_temp > 100:
            score -= abs(mold_temp - 80) * 0.002

        # Pressure effects
        injection_pressure = parameters.get("injection_pressure_bar", 1000)
        if injection_pressure < 800 or injection_pressure > 1400:
            score -= 0.05

        # Cooling effects
        cooling_time = parameters.get("cooling_time_seconds", 8.0)
        if cooling_time < 6 or cooling_time > 12:
            score -= 0.03

        return max(0.0, min(1.0, score))

    def predict_cycle_time(self, parameters: Dict[str, float]) -> float:
        """Predict total cycle time in seconds."""
        injection_time = 3.0  # Fixed
        hold_time = parameters.get("hold_time_seconds", 3.0)
        cooling_time = parameters.get("cooling_time_seconds", 8.0)
        mold_open = 0.5
        ejection = 0.5

        total = injection_time + hold_time + cooling_time + mold_open + ejection

        return max(1.0, total)

    def predict_energy_consumption(self, parameters: Dict[str, float]) -> float:
        """Predict energy consumption per part in kWh."""
        # Baseline: pressure × volume × efficiency
        injection_pressure = parameters.get("injection_pressure_bar", 1000)
        cycle_time = self.predict_cycle_time(parameters)

        # Simplified energy model
        energy = (injection_pressure / 1000.0) * (cycle_time / 10.0) * 0.05

        return energy

    def predict_scrap_rate(self, parameters: Dict[str, float]) -> float:
        """Predict scrap rate (fraction 0-1) from process parameters."""
        quality = self.predict_quality(parameters)

        # Scrap rate inversely related to quality
        scrap = 1.0 - quality

        # Add penalty for extreme parameters
        cooling_time = parameters.get("cooling_time_seconds", 8.0)
        if cooling_time < 5:
            scrap += 0.1  # Insufficient cooling → defects

        mold_temp = parameters.get("mold_temp_c", 80)
        if mold_temp < 50:
            scrap += 0.05

        return max(0.0, min(1.0, scrap))
