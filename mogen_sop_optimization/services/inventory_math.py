"""Pure, deterministic inventory optimization formulae."""

from math import sqrt


class InventoryMath:
    """Formulae used by the Odoo orchestration layer and its tests."""

    @staticmethod
    def fixed_safety_stock(fixed_qty):
        return max(float(fixed_qty or 0.0), 0.0)

    @staticmethod
    def days_of_demand_safety_stock(average_daily_demand, coverage_days):
        return max(float(average_daily_demand or 0.0), 0.0) * max(
            float(coverage_days or 0.0), 0.0
        )

    @staticmethod
    def statistical_safety_stock(
        average_daily_demand,
        demand_standard_deviation,
        service_level_z,
        lead_time_days,
        lead_time_standard_deviation=0.0,
    ):
        """Return demand/lead-time variability safety stock, or zero safely."""
        average = max(float(average_daily_demand or 0.0), 0.0)
        deviation = max(float(demand_standard_deviation or 0.0), 0.0)
        z_value = max(float(service_level_z or 0.0), 0.0)
        lead_time = max(float(lead_time_days or 0.0), 0.0)
        lead_deviation = max(float(lead_time_standard_deviation or 0.0), 0.0)
        if not z_value or not lead_time:
            return 0.0
        variance = lead_time * deviation**2 + average**2 * lead_deviation**2
        return z_value * sqrt(variance)

    @staticmethod
    def reorder_point(average_daily_demand, lead_time_days, safety_stock):
        return max(float(average_daily_demand or 0.0), 0.0) * max(
            float(lead_time_days or 0.0), 0.0
        ) + max(float(safety_stock or 0.0), 0.0)

    @staticmethod
    def eoq(annual_demand, ordering_cost, holding_cost_per_unit):
        demand = max(float(annual_demand or 0.0), 0.0)
        ordering = max(float(ordering_cost or 0.0), 0.0)
        holding = max(float(holding_cost_per_unit or 0.0), 0.0)
        if not demand or not ordering or not holding:
            return 0.0
        return sqrt((2.0 * demand * ordering) / holding)

    @staticmethod
    def xyz_class(average_demand, standard_deviation, x_threshold, y_threshold):
        average = float(average_demand or 0.0)
        if average <= 0.0:
            return "Z"
        coefficient = max(float(standard_deviation or 0.0), 0.0) / average
        if coefficient <= float(x_threshold):
            return "X"
        if coefficient <= float(y_threshold):
            return "Y"
        return "Z"

    @staticmethod
    def abc_classes(consumption_values, a_threshold, b_threshold):
        """Classify ``[(key, annual_consumption_value)]`` deterministically."""
        ordered = sorted(consumption_values, key=lambda item: (-item[1], item[0]))
        total = sum(max(float(value or 0.0), 0.0) for _, value in ordered)
        if not total:
            return {key: "C" for key, _value in ordered}
        classes, cumulative = {}, 0.0
        for key, value in ordered:
            cumulative += max(float(value or 0.0), 0.0)
            percentage = cumulative * 100.0 / total
            if percentage <= float(a_threshold):
                classes[key] = "A"
            elif percentage <= float(b_threshold):
                classes[key] = "B"
            else:
                classes[key] = "C"
        return classes
