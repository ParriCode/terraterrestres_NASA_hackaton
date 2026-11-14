from copy import deepcopy
from dataclasses import asdict, replace
import unittest

from app.models.domain import SimulationConfig, SimulationStatus, SpacecraftState
from app.schemas import SimulationResponse
from app.services.mock_simulation import build_mock_components
from app.services.simulation_service import (
    MAX_STEPS, PropagationOutput, SimulationComponents, SimulationLimitError,
    SimulationNotReadyError, UnknownScenarioError, planned_steps, run_simulation,
)


class SimulationServiceTests(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(
            "mock_earth_moon_v1", SpacecraftState((2e6, 0.0, 0.0), (0.0, 7500.0, 0.0)), 25, 10,
        )
        self.demo = build_mock_components()

    def test_orchestration_order_and_domain_inputs(self):
        calls = []
        before = deepcopy(asdict(self.config))
        def load(scenario_id):
            calls.append("scenario")
            self.assertEqual(scenario_id, self.config.scenario_id)
            return self.demo.load_scenario(scenario_id)
        def propagate(config, scenario):
            calls.append("physics")
            self.assertIs(config, self.config)
            self.assertEqual(scenario.scenario_id, config.scenario_id)
            return self.demo.propagate(config, scenario)
        def diagnose(samples, bodies):
            calls.append("diagnostics")
            self.assertEqual(samples[-1].t_s, self.config.duration_s)
            return self.demo.diagnose(samples, bodies)
        result = run_simulation(self.config, components=SimulationComponents(load, propagate, diagnose))
        self.assertEqual(calls, ["scenario", "physics", "diagnostics"])
        self.assertEqual(asdict(self.config), before)
        self.assertIs(result.config, self.config)
        SimulationResponse.from_domain(result)

    def test_missing_components_are_explicit(self):
        with self.assertRaises(SimulationNotReadyError):
            run_simulation(self.config)

    def test_unknown_scenario_stops_before_propagation(self):
        def propagate(config, scenario):
            self.fail("No debe ejecutarse el motor si no existe el escenario")
        components = replace(self.demo, propagate=propagate)
        with self.assertRaises(UnknownScenarioError):
            run_simulation(replace(self.config, scenario_id="unknown"), components=components)

    def test_mismatched_scenario_is_not_silently_accepted(self):
        def load(scenario_id):
            return replace(self.demo.load_scenario(scenario_id), scenario_id="different")
        with self.assertRaises(RuntimeError):
            run_simulation(self.config, components=replace(self.demo, load_scenario=load))

    def test_partial_propagation_is_sent_to_diagnostics(self):
        def propagate(config, scenario):
            complete = self.demo.propagate(config, scenario)
            return PropagationOutput(SimulationStatus.NUMERICAL_ERROR, complete.samples[:1], [])
        result = run_simulation(self.config, components=replace(self.demo, propagate=propagate))
        self.assertEqual(result.status, SimulationStatus.NUMERICAL_ERROR)
        self.assertEqual(result.diagnostics.final_time_s, 0)
        self.assertEqual(result.diagnostics.steps_completed, 0)
        SimulationResponse.from_domain(result)

    def test_step_limit_is_checked_before_loading_a_scenario(self):
        def load(scenario_id):
            self.fail("No se debe cargar el escenario para una petición excesiva")
        config = replace(self.config, duration_s=MAX_STEPS + 1, step_s=1)
        with self.assertRaises(SimulationLimitError):
            run_simulation(config, components=replace(self.demo, load_scenario=load))

    def test_step_limit_boundary_and_short_final_step(self):
        self.assertEqual(planned_steps(replace(self.config, duration_s=MAX_STEPS, step_s=1)), MAX_STEPS)
        self.assertEqual(planned_steps(self.config), 3)
        self.assertEqual(planned_steps(replace(self.config, step_s=100)), 1)

    def test_each_execution_owns_its_units_mapping(self):
        first = run_simulation(self.config, components=self.demo)
        first.units["length"] = "changed_in_test"
        second = run_simulation(self.config, components=self.demo)
        self.assertEqual(second.units["length"], "m")


if __name__ == "__main__":
    unittest.main()
