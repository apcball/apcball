"""Business rules shared by manual entry, import previews and API-backed models."""
import math


def finite_values(values, names):
    for name in names:
        if not math.isfinite(values.get(name) or 0.0):
            return "%s ต้องเป็นตัวเลขที่มีค่าจำกัด" % name
    return ""


def invoice_error(values):
    error = finite_values(values, ("amount_total", "amount_untaxed", "amount_residual"))
    if error:
        return error
    total, residual = values.get("amount_total", 0), values.get("amount_residual", 0)
    if total and residual and (total > 0) != (residual > 0):
        return "amount_residual: ยอดค้างต้องมีเครื่องหมายเดียวกับยอดรวม"
    if abs(residual) - abs(total) > 0.01:
        return "amount_residual: ยอดค้างมากกว่ายอดรวม"
    if values.get("date_due") and values.get("date") and values["date_due"] < values["date"]:
        return "date_due: วันครบกำหนดต้องไม่ก่อนวันที่เอกสาร"
    return ""


def budget_error(values):
    return finite_values(values, ("amount",)) or period_error(values)


def period_error(values):
    if values.get("date_from") and values.get("date_to") and values["date_to"] < values["date_from"]:
        return "date_to: วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น"
    return ""


def fact_error(values):
    error = finite_values(values, ("amount", "qty"))
    if error:
        return error
    if values.get("kind") == "inventory" and values.get("metric_key") != "inventory_value":
        return "metric_key: สินค้าคงเหลือใช้ inventory_value เท่านั้น"
    if values.get("kind") == "ratio_input" and values.get("label"):
        return "label: ตัวเลขอัตราส่วนไม่ต้องระบุหมวดสินค้า"
    return ""


def company_error(company, related, label):
    if related and related.company_id and related.company_id != company:
        return "%s ต้องเป็นของบริษัทที่เลือกหรือเป็นรายการใช้ร่วมกัน" % label
    return ""
