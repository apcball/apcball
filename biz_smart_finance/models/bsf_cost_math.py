"""Pure, currency-neutral management accounting calculations (no ORM or I/O)."""
import math


def finite_nonnegative(*values):
    return all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values)


def cost_metrics(sales, variable, fixed, one_off=0, target=0, complete=True):
    contribution = sales - variable
    rate = contribution / sales if sales > 0 else None
    reason = ("ข้อมูลยังไม่ครบ" if not complete else
              "ยอดขายต้องมากกว่าศูนย์" if sales <= 0 else
              "กำไรส่วนเกินไม่เป็นบวก — เพิ่มยอดขายด้วยโครงสร้างเดิมยังไม่คุ้มทุน"
              if rate <= 0 else "")
    valid = not reason
    breakeven = (fixed + one_off) / rate if valid else None
    return {
        "sales": sales, "variable": variable, "fixed": fixed, "one_off": one_off,
        "contribution": contribution, "contribution_pct": rate * 100 if rate is not None else None,
        "operating_profit": contribution - fixed - one_off,
        "recurring_profit": contribution - fixed,
        "break_even": breakeven,
        "recurring_break_even": fixed / rate if valid else None,
        "target_sales": (fixed + one_off + target) / rate if valid else None,
        "sales_gap": max(0, breakeven - sales) if valid else None,
        "safety_margin": sales - breakeven if valid else None,
        "reason": reason,
    }


def normalized_savings(base_sales, base_variable, base_fixed, actual_sales,
                       actual_variable, actual_fixed):
    """Flexible budget: lower activity alone is never booked as variable savings."""
    if base_sales <= 0:
        return None
    return (base_variable / base_sales * actual_sales - actual_variable
            + base_fixed - actual_fixed)
