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


def build_line_mismatch_message(line, bad_axes):
    """Message for a stock.move.line whose location(s) fall outside the
    subtree of the matching move-header location. `bad_axes` is a subset
    of {"source", "dest"}.
    """
    move = line.move_id
    ref = move.reference or move.display_name
    detail = []
    if "source" in bad_axes:
        detail.append(_(
            "  ต้นทาง: line = %(l)s / header = %(h)s"
        ) % {"l": line.location_id.complete_name or "-",
             "h": move.location_id.complete_name or "-"})
    if "dest" in bad_axes:
        detail.append(_(
            "  ปลายทาง: line = %(l)s / header = %(h)s"
        ) % {"l": line.location_dest_id.complete_name or "-",
             "h": move.location_dest_id.complete_name or "-"})
    return _(
        "Move line ของ %(ref)s อยู่คนละคลัง/สาขากับ location บน move header\n"
        "%(detail)s\n\n"
        "สาเหตุ: valuation (FIFO / stock.valuation.layer) ยึดตาม move header "
        "ส่วน stock จริงยึดตาม move line — ถ้าต่างคลังกัน รายงานมูลค่ากับของจริง "
        "จะไม่ตรง โดยไม่มีการแจ้งเตือน\n"
        "แก้: ตั้ง Source/Destination Location บน move header ให้ตรงกับที่สินค้าไปจริง\n"
        "  • Unbuild หลายคลัง: ตั้ง Destination Location แยกต่อ component "
        "(ระบบจะสร้าง move header ต่อ component ให้เอง)\n"
        "  • Repair script: with_context(skip_location_consistency_check=True)"
    ) % {"ref": ref, "detail": "\n".join(detail)}


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
