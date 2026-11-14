"""
Se ejecutan desde la carpeta backend, con el app.models.domain real del equipo.
Los dobles de Scenario solo sustituyen al proveedor de efemerides; no se
modifican los modelos compartidos ni la API publica.
"""

import math
import unittest
from types import SimpleNamespace

from app.models.domain import SpacecraftState, SimulationStatus
from app.physics.dynamics import state_derivative
from app.physics.events import is_collision, segment_min_distance_sq
from app.physics.gravity import gravitational_acceleration
from app.physics.rk2 import integrate, rk2_step


class FakeScenario:
    def __init__(self, bodies, position_functions):
        self._bodies = bodies
        self._position_functions = position_functions
        self.queries = []

    def get_bodies(self):
        return self._bodies

    def get_body_pos(self, body, t_s):
        self.queries.append((body.id, t_s))
        return self._position_functions[body.id](t_s)


def body(body_id="earth", mu=1e-9, radius=1.0):
    return SimpleNamespace(id=body_id, mu_m3_s2=mu, radius_m=radius)


def config(position, velocity, duration=1.0, step=1.0):
    # integrate solo lee estos 3 campos de SimulationConfig; evita
    # depender del constructor del modelo, que mantiene Angel.
    return SimpleNamespace(
        initial_state=SpacecraftState(position_m=position, velocity_m_s=velocity),
        duration_s=duration,
        step_s=step,
    )


class LiPhysicsTests(unittest.TestCase):
    def test_gravity_attracts_toward_body(self):
        acceleration = gravitational_acceleration(
            (10.0, 0.0, 0.0), {"earth": (0.0, 0.0, 0.0)},
            [body(mu=100.0)],
        )
        self.assertAlmostEqual(acceleration[0], -1.0)
        self.assertAlmostEqual(acceleration[1], 0.0)

    def test_dynamics_uses_scenario_not_body_pos(self):
        s = FakeScenario([body(mu=10.0)], {"earth": lambda t: (0.0, 0.0, 0.0)})
        state = SpacecraftState(position_m=(10.0, 0.0, 0.0), velocity_m_s=(1.0, 0.0, 0.0))
        velocity, acceleration = state_derivative(2.5, state, s)
        self.assertEqual(velocity, (1.0, 0.0, 0.0))
        self.assertAlmostEqual(acceleration[0], -0.1)
        self.assertIn(("earth", 2.5), s.queries)

    def test_rk2_queries_midpoint_of_moving_body(self):
        s = FakeScenario(
            [body(mu=1e-9)],
            {"earth": lambda t: (1000.0 + t, 0.0, 0.0)},
        )
        state = SpacecraftState(position_m=(0.0, 0.0, 0.0), velocity_m_s=(10.0, 0.0, 0.0))
        result = rk2_step(0.0, state, 1.0, s)
        self.assertAlmostEqual(result.position_m[0], 10.0, places=7)
        self.assertIn(("earth", 0.5), s.queries)

    def test_duration_not_multiple_of_step(self):
        s = FakeScenario([body(mu=1e-12)], {"earth": lambda t: (1e9, 0.0, 0.0)})
        samples, events, status = integrate(
            config((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), duration=2.5, step=1.0), s,
        )
        self.assertEqual(status, SimulationStatus.COMPLETED)
        self.assertEqual([sample.t_s for sample in samples], [0.0, 1.0, 2.0, 2.5])
        self.assertFalse(events)
        for sample in samples:
            self.assertEqual(sample.body_positions_m["earth"], (1e9, 0.0, 0.0))

    def test_collision_at_initial_state(self):
        s = FakeScenario([body()], {"earth": lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(config((0.5, 0, 0), (0, 0, 0)), s)
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(len(samples), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].t_s, 0.0)
        self.assertEqual(events[0].body_id, "earth")

    def test_impact_during_step_has_event_and_consistent_sample(self):
        s = FakeScenario([body()], {"earth": lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(
            config((-2.0, 0, 0), (2.0, 0, 0), duration=2, step=2), s,
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].t_s, 0.5, delta=0.003)
        self.assertEqual(events[0].t_s, samples[-1].t_s)
        self.assertEqual(events[0].position_m, samples[-1].spacecraft.position_m)
        self.assertEqual(samples[-1].body_positions_m["earth"], (0.0, 0.0, 0.0))
        self.assertEqual(events[0].body_id, "earth")
        self.assertTrue(all(a.t_s < b.t_s for a, b in zip(samples, samples[1:])))

    def test_fast_crossing_between_original_step_endpoints(self):
        s = FakeScenario([body()], {"earth": lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(
            config((-10.0, 0.0, 0.0), (40.0, 0.0, 0.0), duration=1, step=1), s,
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertAlmostEqual(events[0].t_s, 0.225, delta=0.005)
        self.assertLess(samples[-1].t_s, 1.0)

    def test_grazing_flyby_does_not_collide(self):
        s = FakeScenario([body()], {"earth": lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(
            config((-10.0, 1.1, 0), (40.0, 0, 0), duration=0.5, step=0.5), s,
        )
        self.assertEqual(status, SimulationStatus.COMPLETED)
        self.assertFalse(events)
        self.assertAlmostEqual(samples[-1].t_s, 0.5)

    def test_moving_body_positions_match_sample_times(self):
        s = FakeScenario([body(mu=1e-12)], {"earth": lambda t: (1000.0 + 2 * t, 0.0, 0.0)})
        samples, events, status = integrate(
            config((0.0, 0, 0), (0.0, 0, 0), duration=2, step=0.5), s,
        )
        self.assertEqual(status, SimulationStatus.COMPLETED)
        for sample in samples:
            self.assertAlmostEqual(sample.body_positions_m["earth"][0], 1000.0 + 2 * sample.t_s)

    def test_segment_geometry_detects_full_crossing(self):
        self.assertEqual(
            segment_min_distance_sq((-10, 0, 0), (10, 0, 0), (0, 0, 0), (0, 0, 0)), 0.0,
        )
        self.assertGreater(
            segment_min_distance_sq((-10, 2, 0), (10, 2, 0), (0, 0, 0), (0, 0, 0)), 1.0,
        )

    def test_realistic_earth_impact(self):
        earth = body(mu=3.986004418e14, radius=6_371_000.0)
        s = FakeScenario([earth], {"earth": lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(
            config((1e7, 0.0, 0.0), (-2000.0, 0.0, 0.0),
                   duration=2000.0, step=1800.0), s,
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].body_id, "earth")
        self.assertAlmostEqual(math.dist(samples[-1].spacecraft.position_m, (0, 0, 0)),
                               earth.radius_m, delta=20.0)

    def test_two_bodies_contribute_to_acceleration(self):
        s = FakeScenario(
            [body('earth', mu=100.0), body('moon', mu=25.0)],
            {'earth': lambda t: (0.0, 0.0, 0.0),
             'moon': lambda t: (20.0, 0.0, 0.0)},
        )
        state = SpacecraftState(position_m=(10.0, 0.0, 0.0),
                                velocity_m_s=(0.0, 0.0, 0.0))
        _, acceleration = state_derivative(0.0, state, s)
        self.assertAlmostEqual(acceleration[0], -0.75)

    def test_moon_impact_reports_moon_not_earth(self):
        earth = body('earth', mu=3.986004418e14, radius=6_371_000.0)
        moon = body('moon', mu=4.9048695e12, radius=1_737_400.0)
        s = FakeScenario(
            [earth, moon],
            {'earth': lambda t: (0.0, 0.0, 0.0),
             'moon': lambda t: (384_400_000.0, 0.0, 0.0)},
        )
        samples, events, status = integrate(
            config((360_000_000.0, 0.0, 0.0), (500.0, 0.0, 0.0),
                   duration=7 * 86_400, step=3600), s,
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].body_id, 'moon')
        self.assertEqual(events[0].t_s, samples[-1].t_s)

    def test_refined_orbit_converges(self):
        mu = 3.986004418e14
        radius_orbit = 1e7
        speed = math.sqrt(mu / radius_orbit)
        period = 2 * math.pi * radius_orbit / speed
        s = FakeScenario([body(mu=mu, radius=6.371e6)],
                         {"earth": lambda t: (0.0, 0.0, 0.0)})
        def error(step):
            trajectory, _, status = integrate(
                config((radius_orbit, 0, 0), (0, speed, 0), period, step), s
            )
            self.assertEqual(status, SimulationStatus.COMPLETED)
            return math.dist(trajectory[-1].spacecraft.position_m, (radius_orbit, 0, 0))
        coarse = error(60.0)
        fine = error(30.0)
        self.assertGreater(coarse, 3.0 * fine)
        self.assertLess(coarse, 5.0 * fine)



class LiRegressionTests(unittest.TestCase):
    """Regression cases for failures in the supplied physics.zip."""

    def test_midpoint_inside_body_is_collision_not_numerical_error(self):
        # The original code evaluates gravity at x=0 when dt=2 and reports
        # NUMERICAL_ERROR rather than detecting the surface crossing at 0.5 s.
        scenario = FakeScenario([body(mu=1e-12)], {'earth': lambda t: (0.0, 0.0, 0.0)})
        samples, events, status = integrate(
            config((-2.0, 0.0, 0.0), (2.0, 0.0, 0.0), duration=2.0, step=2.0),
            scenario,
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].t_s, 0.5, delta=0.003)

    def test_no_collision_moving_body_crosses_but_relative_path_safe(self):
        # Check relative geometry uses both body positions, not just x=0.
        scenario = FakeScenario(
            [body(mu=1e-12, radius=1.0)],
            {'earth': lambda t: (20.0*t, 2.0, 0.0)},
        )
        samples, events, status = integrate(
            config((0.0, 0.0, 0.0), (20.0, 0.0, 0.0), 1.0, 1.0), scenario
        )
        self.assertEqual(status, SimulationStatus.COMPLETED)
        self.assertEqual(len(events), 0)
        self.assertAlmostEqual(samples[-1].t_s, 1.0)

    def test_invalid_initial_state_fails_early(self):
        scenario = FakeScenario([body()], {'earth': lambda t: (0., 0., 0.)})
        with self.assertRaises(ValueError):
            integrate(config((float('nan'), 0., 0.), (0., 0., 0.)), scenario)

    def test_duplicate_body_ids_rejected(self):
        scenario = FakeScenario(
            [body('earth'), body('earth')], {'earth': lambda t: (0., 0., 0.)}
        )
        with self.assertRaises(ValueError):
            integrate(config((2., 0., 0.), (1., 0., 0.)), scenario)

    def test_gravity_rejects_invalid_body_data(self):
        with self.assertRaises(ValueError):
            gravitational_acceleration((5., 0., 0.), {'earth': (0., 0., 0.)},
                                      [body(mu=-10.)])
        with self.assertRaises(ValueError):
            gravitational_acceleration((float('inf'), 0., 0.),
                                      {'earth': (0., 0., 0.)}, [body()])

    def test_exact_surface_counts_as_impact(self):
        s = FakeScenario([body(radius=1.)], {'earth': lambda t: (0., 0., 0.)})
        samples, events, status = integrate(config((1., 0., 0.), (0., 1., 0.)), s)
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertEqual(events[0].t_s, 0.0)
        self.assertEqual(len(samples), 1)

    def test_public_compatibility_helpers(self):
        from app.physics.events import find_colliding_body, _find_colliding_body
        from app.physics.events import swept_collision_closest_fraction
        state = SpacecraftState((0., 0., 0.), (0., 0., 0.))
        object_body = body(radius=1.)
        self.assertIs(find_colliding_body(state, {'earth': (0., 0., 0.)}, [object_body]), object_body)
        self.assertIs(_find_colliding_body(state, {'earth': (0., 0., 0.)}, [object_body]), object_body)
        self.assertAlmostEqual(swept_collision_closest_fraction(
            (-2., 0., 0.), (2., 0., 0.), (0., 0., 0.), (0., 0., 0.), 1.0), 0.5)
        self.assertIsNone(swept_collision_closest_fraction(
            (-2., 2., 0.), (2., 2., 0.), (0., 0., 0.), (0., 0., 0.), 1.0))

    def test_legacy_body_pos_variant_still_supported(self):
        # The user ZIP directly calls body.pos(t). Both variants use exactly
        # the same provider for derivatives and stored samples.
        moving = SimpleNamespace(id="earth", mu_m3_s2=1e-12,
                                 radius_m=1., pos=lambda t: (100. + t, 0., 0.))
        class LegacyScenario:
            def get_bodies(self):
                return [moving]
        samples, events, status = integrate(
            config((0., 0., 0.), (0., 1., 0.), duration=1., step=1.), LegacyScenario()
        )
        self.assertEqual(status, SimulationStatus.COMPLETED)
        self.assertAlmostEqual(samples[-1].body_positions_m["earth"][0], 101.)

    def test_invalid_initial_ephemeris_is_not_saved(self):
        s = FakeScenario([body()], {'earth': lambda t: (float('nan'), 0., 0.)})
        samples, events, status = integrate(config((2., 0., 0.), (0., 0., 0.)), s)
        self.assertEqual(status, SimulationStatus.NUMERICAL_ERROR)
        self.assertFalse(samples)
        self.assertFalse(events)

    def test_invalid_duration_rejected(self):
        s = FakeScenario([body()], {'earth': lambda t: (0., 0., 0.)})
        with self.assertRaises(ValueError):
            integrate(config((2., 0., 0.), (0., 0., 0.), 0., 1.), s)

    def test_impact_sample_matches_moving_body_instant(self):
        # Moving body: impact positions must be computed at impact time,
        # not copied from the beginning or end of the step.
        s = FakeScenario([body(mu=1e-12)],
                         {'earth': lambda t: (t, 0., 0.)})
        samples, events, status = integrate(
            config((-2., 0., 0.), (3., 0., 0.), 2., 2.), s
        )
        self.assertEqual(status, SimulationStatus.COLLISION)
        self.assertAlmostEqual(events[0].t_s, 0.5, delta=0.005)
        self.assertEqual(samples[-1].body_positions_m['earth'],
                         (samples[-1].t_s, 0., 0.))

    def test_numerical_error_never_appends_nonfinite_sample(self):
        s = FakeScenario([body(mu=1e-12)],
                         {'earth': lambda t: (100., 0., 0.) if t < .5 else (float('nan'), 0., 0.)})
        samples, events, status = integrate(
            config((0., 0., 0.), (1., 0., 0.), 1., 1.), s
        )
        self.assertEqual(status, SimulationStatus.NUMERICAL_ERROR)
        self.assertFalse(events)
        self.assertEqual(len(samples), 1)


if __name__ == "__main__":
    unittest.main()