from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.controllers.simulation_controller import get_simulation_runner
from app.main import create_app
from app.models.domain import (
    DEFAULT_UNITS, Event, EventType, SimulationConfig, SimulationResult,
    SimulationStatus,
)
from app.schemas import SimulationResponse
from app.services.mock_simulation import MOCK_WARNING, build_mock_components, diagnose_mock
from app.services.simulation_service import MAX_STEPS, run_simulation

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
LOGGER = "app.controllers.simulation_controller"


class SimulationApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(simulation_mode="mock", cors_origins=["http://localhost:5173"])
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.payload = json.loads((EXAMPLES / "request.mock.json").read_text())

    def post(self, payload=None, **kwargs):
        return self.client.post("/simulations", json=self.payload if payload is None else payload, **kwargs)

    def override_runner(self, runner):
        self.app.dependency_overrides[get_simulation_runner] = lambda: runner

    def test_health_identifies_mock(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["simulation_mode"], "mock")
        self.assertTrue(response.json()["simulation_ready"])
        self.assertIn("FICTICIOS", response.json()["notice"])

    def test_valid_request_preserves_contract_and_initial_state(self):
        original = deepcopy(self.payload)
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(self.payload, original)
        self.assertEqual(result["config"], original)
        self.assertEqual(result["samples"][0]["spacecraft"], original["initial_state"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["units"], DEFAULT_UNITS)
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(set(result), {
            "schema_version", "config", "frame", "units", "bodies", "status",
            "samples", "events", "diagnostics",
        })
        SimulationResponse.model_validate(result)

    def test_mock_is_identified_in_headers_and_existing_body_fields(self):
        response = self.post()
        self.assertEqual(response.headers["x-simulation-mode"], "mock")
        self.assertEqual(response.headers["x-simulation-warning"], MOCK_WARNING)
        self.assertTrue(response.json()["config"]["scenario_id"].startswith("mock_"))
        for body in response.json()["bodies"]:
            self.assertIn("ficticios", body["name"])
            self.assertGreater(body["mass"], 0)

    def test_mock_motion_and_diagnostics_match_saved_samples(self):
        result = self.post().json()
        self.assertEqual([sample["t_s"] for sample in result["samples"]], [0, 10, 20, 30, 40, 50, 60])
        for sample in result["samples"]:
            self.assertEqual(sample["spacecraft"]["position_m"], [2000000, 7500 * sample["t_s"], 0])
            self.assertEqual(set(sample["body_positions_m"]), {"earth", "moon"})
        for body in result["bodies"]:
            expected = min(math.dist(s["spacecraft"]["position_m"], s["body_positions_m"][body["id"]]) for s in result["samples"])
            self.assertEqual(result["diagnostics"]["min_distance_m"][body["id"]], expected)
            self.assertEqual(result["diagnostics"]["min_altitude_m"][body["id"]], expected - body["radius_m"])

    def test_last_step_is_shortened(self):
        self.payload["duration_s"] = 25
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([s["t_s"] for s in response.json()["samples"]], [0, 10, 20, 25])

    def test_step_larger_than_duration_is_valid(self):
        self.payload.update(duration_s=5, step_s=100)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([s["t_s"] for s in response.json()["samples"]], [0, 5])

    def test_fractional_steps_do_not_duplicate_the_final_sample(self):
        self.payload.update(duration_s=0.30000000000000004, step_s=0.1)
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        times = [s["t_s"] for s in response.json()["samples"]]
        self.assertEqual(times[-1], self.payload["duration_s"])
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))

    def test_tiny_duration_remains_valid(self):
        self.payload.update(duration_s=1e-308, step_s=1e308)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["samples"][-1]["t_s"], 1e-308)

    def test_invalid_duration_and_step_are_rejected_before_service(self):
        called = []
        self.override_runner(lambda config: called.append(config))
        for field in ("duration_s", "step_s"):
            for value in (0, -1, True, "10", None):
                with self.subTest(field=field, value=value):
                    payload = deepcopy(self.payload)
                    payload[field] = value
                    response = self.post(payload)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()["detail"]["code"], "invalid_request")
        self.assertEqual(called, [])

    def test_vectors_have_exactly_three_numeric_components(self):
        for field in ("position_m", "velocity_m_s"):
            for vector in ([1, 2], [1, 2, 3, 4], [True, 0, 0], ["1", 0, 0]):
                with self.subTest(field=field, vector=vector):
                    payload = deepcopy(self.payload)
                    payload["initial_state"][field] = vector
                    self.assertEqual(self.post(payload).status_code, 422)

    def test_nonfinite_numbers_return_json_422_instead_of_500(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            for location in ("duration_s", "position_m"):
                with self.subTest(value=value, location=location):
                    payload = deepcopy(self.payload)
                    if location == "duration_s":
                        payload[location] = value
                    else:
                        payload["initial_state"][location][0] = value
                    response = self.client.post("/simulations", content=json.dumps(payload), headers={"Content-Type": "application/json"})
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()["detail"]["code"], "invalid_request")
                    self.assertNotIn('"input"', response.text)

    def test_missing_unknown_and_blank_fields_are_rejected(self):
        cases = []
        payload = deepcopy(self.payload)
        del payload["initial_state"]
        cases.append(payload)
        cases.append({**self.payload, "mass_kg": 10})
        cases.append({**self.payload, "scenario_id": " "})
        payload = deepcopy(self.payload)
        payload["initial_state"]["t_s"] = 0
        cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload).status_code, 422)

    def test_malformed_json_is_a_structured_validation_error(self):
        response = self.client.post("/simulations", content='{"broken":', headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_request")

    def test_unknown_scenario_does_not_fall_back_to_mock(self):
        self.payload["scenario_id"] = "earth_moon_circular_v1"
        response = self.post()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "unknown_scenario")

    def test_too_many_steps_and_overflowing_ratio_are_rejected(self):
        for duration, step in ((MAX_STEPS + 1, 1), (1e308, 1e-308)):
            with self.subTest(duration=duration, step=step):
                self.payload.update(duration_s=duration, step_s=step)
                response = self.post()
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["code"], "simulation_limit_exceeded")

    def test_numerical_overflow_returns_only_valid_partial_samples(self):
        self.payload.update(duration_s=10, step_s=1)
        self.payload["initial_state"]["velocity_m_s"] = [1e308, 0, 0]
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "numerical_error")
        self.assertEqual(result["diagnostics"]["final_time_s"], 1)
        self.assertEqual(len(result["samples"]), 2)
        for sample in result["samples"]:
            self.assertTrue(all(math.isfinite(n) for n in sample["spacecraft"]["position_m"]))

    def test_unrepresentable_initial_distances_are_rejected(self):
        self.payload["initial_state"]["position_m"] = [1.7e308] * 3
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_initial_state")

    def test_controller_passes_real_domain_objects_to_runner(self):
        observed = []
        def runner(config):
            observed.append(config)
            return run_simulation(config, components=build_mock_components())
        self.override_runner(runner)
        self.assertEqual(self.post().status_code, 200)
        self.assertIsInstance(observed[0], SimulationConfig)
        self.assertIsInstance(observed[0].initial_state.position_m, tuple)

    def test_collision_is_http_200_not_an_api_error(self):
        def runner(config):
            # Suceso sintético: prueba el transporte del evento, no su física.
            result = run_simulation(config, components=build_mock_components())
            samples = result.samples[:1]
            return SimulationResult(
                config=config, bodies=result.bodies, status=SimulationStatus.COLLISION,
                samples=samples,
                events=[Event(EventType.COLLISION, 0.0, "earth", config.initial_state.position_m)],
                diagnostics=diagnose_mock(samples, result.bodies),
            )
        self.override_runner(runner)
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "collision")
        self.assertEqual(response.json()["events"][0]["type"], "collision")

    def test_unexpected_errors_are_logged_and_not_exposed(self):
        def fail(config):
            raise RuntimeError("private_internal_detail")
        self.override_runner(fail)
        with self.assertLogs(LOGGER, level="ERROR"):
            response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "simulation_failed")
        self.assertNotIn("private_internal_detail", response.text)
        self.assertEqual(response.headers["x-simulation-mode"], "mock")

    def test_invalid_engine_output_is_a_server_error(self):
        def invalid_output(config):
            result = run_simulation(config, components=build_mock_components())
            result.bodies[0] = replace(result.bodies[0], mass=-1)
            return result
        self.override_runner(invalid_output)
        with self.assertLogs(LOGGER, level="ERROR"):
            response = self.post()
        self.assertEqual(response.status_code, 500)

    def test_real_mode_returns_503_until_components_are_connected(self):
        with TestClient(create_app(simulation_mode="real")) as client:
            health = client.get("/health").json()
            self.assertFalse(health["simulation_ready"])
            response = client.post("/simulations", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "simulation_not_ready")
        self.assertEqual(response.headers["x-simulation-mode"], "real")
        self.assertNotIn("x-simulation-warning", response.headers)

    def test_cors_allows_react_and_exposes_mock_headers(self):
        origin = "http://localhost:5173"
        preflight = self.client.options("/simulations", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        })
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], origin)
        response = self.post(headers={"Origin": origin})
        self.assertEqual(response.headers["access-control-allow-origin"], origin)
        self.assertIn("X-Simulation-Mode", response.headers["access-control-expose-headers"])
        self.assertIn("X-Simulation-Warning", response.headers["access-control-expose-headers"])

    def test_cors_rejects_an_unconfigured_origin(self):
        response = self.client.options("/simulations", headers={
            "Origin": "https://unconfigured.example", "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_invalid_requests_from_react_keep_cors_headers(self):
        response = self.post({**self.payload, "step_s": 0}, headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_environment_settings_are_applied(self):
        with patch.dict("os.environ", {"ORBITAL_SIMULATION_MODE": "real", "ORBITAL_CORS_ORIGINS": "http://localhost:4444"}):
            with TestClient(create_app()) as client:
                self.assertEqual(client.get("/health").json()["simulation_mode"], "real")
                response = client.options("/simulations", headers={"Origin": "http://localhost:4444", "Access-Control-Request-Method": "POST"})
                self.assertEqual(response.status_code, 200)

    def test_invalid_mode_is_rejected_at_startup(self):
        with self.assertRaises(ValueError):
            create_app(simulation_mode="unknown")

    def test_interactive_docs_describe_contract_and_mock(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        operation = schema["paths"]["/simulations"]["post"]
        self.assertIn("ficticios", operation["summary"])
        self.assertIn("X-Simulation-Mode", operation["responses"]["200"]["headers"])
        self.assertIn("mass", schema["components"]["schemas"]["CelestialBodySchema"]["required"])

    def test_invalid_example_file_returns_422(self):
        payload = json.loads((EXAMPLES / "request.invalid.json").read_text())
        self.assertEqual(self.post(payload).status_code, 422)

    def test_repeated_requests_are_deterministic_and_independent(self):
        first = self.post().json()
        other = deepcopy(self.payload)
        other["initial_state"]["position_m"][0] += 1000
        self.assertEqual(self.post(other).status_code, 200)
        self.assertEqual(self.post().json(), first)


if __name__ == "__main__":
    unittest.main()
