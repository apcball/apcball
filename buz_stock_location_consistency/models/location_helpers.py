# -*- coding: utf-8 -*-
"""Pure helpers shared by the stock.move / stock.picking guards."""
from odoo import _


def loc_contained(child_loc, parent_loc):
    """Return True if child_loc is parent_loc or a descendant of it.

    Uses Odoo's materialized `parent_path` ("1/5/27/"): a descendant's
    path is prefixed by its ancestor's path, and a location's path is a
    prefix of itself, so equality also returns True.

    Conservative on missing data: if either record is empty or its
    parent_path is not yet computed, containment cannot be disproven,
    so return True (never block on incomplete data).
    """
    if not child_loc or not parent_loc:
        return True
    child_path = child_loc.parent_path
    parent_path = parent_loc.parent_path
    if not child_path or not parent_path:
        return True
    return child_path.startswith(parent_path)


def build_mismatch_message(move, bad_lines, new_location):
    ref = move.reference or move.display_name
    ml_locs = ", ".join(sorted(set(bad_lines.mapped("location_id.complete_name"))))
    return _(
        "ไม่สามารถเปลี่ยนตำแหน่งต้นทาง (Source Location) ของเอกสารที่ยืนยันแล้ว (Done) ได้\n"
        "อ้างอิง: %(ref)s\n"
        "Move line อยู่ที่: %(ml)s\n"
        "Header จะเปลี่ยนเป็น: %(new)s\n\n"
        "สาเหตุ: การเปลี่ยน header อย่างเดียวจะทำให้ move line กับ valuation (FIFO) "
        "ไม่ตรงกับ stock จริง โดยไม่มีการแจ้งเตือน\n"
        "กรุณาใช้ Inventory Adjustment / Return เพื่อย้าย stock ให้ถูกต้อง\n\n"
        "(To bypass in a deliberate repair script: "
        "with_context(skip_location_consistency_check=True))"
    ) % {"ref": ref, "ml": ml_locs, "new": new_location.complete_name or str(new_location.id)}
