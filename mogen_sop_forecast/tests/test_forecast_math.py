from odoo.tests.common import TransactionCase

from odoo.addons.mogen_sop_forecast.services.forecast_math import ForecastMath


class TestForecastMath(TransactionCase):
    def test_supported_deterministic_methods(self):
        history = [10.0, 20.0, 30.0, 40.0]
        self.assertEqual(ForecastMath.moving_average(history, 3), 30.0)
        self.assertEqual(ForecastMath.weighted_moving_average(history, [1, 2, 3]), 200.0 / 6.0)
        self.assertAlmostEqual(ForecastMath.exponential_smoothing(history, 0.5), 31.25)
        self.assertEqual(ForecastMath.linear_trend(history), 50.0)
        self.assertEqual(ForecastMath.seasonal_naive(history, 2), 30.0)
        self.assertEqual(ForecastMath.same_period_last_year(history, 2), 30.0)

    def test_croston_and_insufficient_history(self):
        self.assertAlmostEqual(ForecastMath.croston([0.0, 4.0, 0.0, 0.0, 6.0], 0.2), 4.4 / 3.0)
        self.assertIsNone(ForecastMath.moving_average([10.0], 3))
        self.assertIsNone(ForecastMath.linear_trend([10.0]))
