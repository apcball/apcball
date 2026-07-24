"""Deterministic, dependency-free forecasting formulas."""

from math import sqrt


class ForecastMath:
    @staticmethod
    def moving_average(history, periods):
        values = history[-periods:]
        if periods <= 0 or len(values) < periods:
            return None
        return sum(values) / periods

    @staticmethod
    def weighted_moving_average(history, weights):
        if not weights or len(history) < len(weights):
            return None
        values = history[-len(weights):]
        total_weight = sum(weights)
        if total_weight <= 0:
            return None
        return sum(value * weight for value, weight in zip(values, weights)) / total_weight

    @staticmethod
    def exponential_smoothing(history, alpha):
        if not history or not 0 < alpha <= 1:
            return None
        estimate = history[0]
        for value in history[1:]:
            estimate = alpha * value + (1 - alpha) * estimate
        return estimate

    @staticmethod
    def linear_trend(history):
        count = len(history)
        if count < 2:
            return None
        x_mean = (count - 1) / 2
        y_mean = sum(history) / count
        denominator = sum((index - x_mean) ** 2 for index in range(count))
        if not denominator:
            return None
        slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(history)) / denominator
        return max(0.0, y_mean + slope * count)

    @staticmethod
    def seasonal_naive(history, seasonal_periods):
        if seasonal_periods <= 0 or len(history) < seasonal_periods:
            return None
        return history[-seasonal_periods]

    @staticmethod
    def same_period_last_year(history, seasonal_periods):
        return ForecastMath.seasonal_naive(history, seasonal_periods)

    @staticmethod
    def croston(history, alpha):
        non_zero = [(index, value) for index, value in enumerate(history) if value > 0]
        if len(non_zero) < 2 or not 0 < alpha <= 1:
            return None
        first_index, demand_estimate = non_zero[0]
        interval_estimate = None
        previous_index = first_index
        for index, value in non_zero[1:]:
            interval = index - previous_index
            interval_estimate = interval if interval_estimate is None else alpha * interval + (1 - alpha) * interval_estimate
            demand_estimate = alpha * value + (1 - alpha) * demand_estimate
            previous_index = index
        return demand_estimate / interval_estimate if interval_estimate else None

    @staticmethod
    def standard_deviation(history):
        if len(history) < 2:
            return None
        mean = sum(history) / len(history)
        return sqrt(sum((value - mean) ** 2 for value in history) / (len(history) - 1))
