
# -*- coding: utf-8 -*-
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_transit_receipt = fields.Boolean(compute="_compute_is_transit_receipt", store=False)

    def _compute_is_transit_receipt(self):
        for p in self:
            p.is_transit_receipt = (
                p.picking_type_id.code == "incoming"
                and p.location_dest_id
                and p.location_dest_id.usage == "transit"
                and p.state == "done"
            )

    def action_open_transit_transfer_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "transit.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_source_location_id": self.location_dest_id.id,
            },
        }

    # --- Force valuation for inter-warehouse internal transfers ---
    def _get_warehouse_for_location(self, location):
        """Return the warehouse owning or containing the given location.
        Uses parent_of on lot_stock_id to find the closest warehouse.
        """
        if not location:
            return self.env["stock.warehouse"]
        return self.env["stock.warehouse"].search([("lot_stock_id", "parent_of", location.id)], limit=1)

    def _needs_force_valuation(self):
        """Decide if this picking should create valuation on validate.
        We force valuation when:
        - Operation is Internal, and
        - Both source and destination are internal-like locations, and
        - Source and destination belong to different warehouses.
        """
        self.ensure_one()
        if self.picking_type_id.code != "internal":
            return False
        src = self.location_id
        dst = self.location_dest_id
        if not src or not dst:
            return False
        if src.usage != "internal" or dst.usage != "internal":
            return False
        wh_src = self._get_warehouse_for_location(src)
        wh_dst = self._get_warehouse_for_location(dst)
        if not wh_src or not wh_dst:
            return False
        needs = wh_src.id != wh_dst.id
        _logger.info("[tqt] Picking %s inter-warehouse=%s (from %s to %s)", self.name, needs, wh_src.display_name, wh_dst.display_name)
        return needs

    def button_validate(self):
        """Override to force valuation for inter-warehouse internal transfers.
        Ensures SVL and accounting entries are produced using our move overrides.
        """
        force = any(p._needs_force_valuation() for p in self)
        if not force:
            return super().button_validate()

        _logger.info("[tqt] Force valuation on validate for pickings: %s", ", ".join(self.mapped("name")))

        # Ensure moves have a reasonable price_unit fallback before validation
        for move in self.move_ids:
            try:
                if not getattr(move, "price_unit", 0):
                    # fallback to product standard price
                    move.price_unit = move.product_id.standard_price or 0.0
            except Exception as e:
                _logger.debug("[tqt] Could not set price_unit for move %s: %s", move.id, e)

        # Validate with force_valuation so SVL is created
        result = super(StockPicking, self.with_context(force_valuation=True)).button_validate()

        # Best-effort: for internal inter-warehouse moves, also generate accounting entries
        try:
            for picking in self:
                if not picking._needs_force_valuation():
                    continue
                # Only done moves
                done_moves = picking.move_ids.filtered(lambda m: m.state == 'done' and m.product_id.type == 'product')
                for move in done_moves.with_context(force_valuation=True):
                    try:
                        # If there is no related account move yet, attempt to create it
                        # This calls our overridden _account_entry_move which will honor force_valuation
                        move._account_entry_move()
                    except Exception as e:
                        _logger.warning("[tqt] Could not create accounting entry for move %s: %s", move.id, e)
        except Exception as e:
            _logger.debug("[tqt] Post-validate accounting entries skipped: %s", e)

        return result

    def action_rebuild_valuation(self):
        """Best-effort rebuild of stock valuation and accounting entries for this picking.
        Useful when a transfer was validated but no valuation occurred.
        """
        for picking in self:
            _logger.info("[tqt] Rebuild valuation for picking %s", picking.name)
            done_moves = picking.move_ids.filtered(lambda m: m.state == 'done' and m.product_id.type == 'product')
            for move in done_moves:
                try:
                    # Ensure price_unit fallback
                    if not getattr(move, 'price_unit', 0):
                        try:
                            move.price_unit = move._get_price_unit() or move.product_id.standard_price or 0.0
                        except Exception:
                            move.price_unit = move.product_id.standard_price or 0.0

                    # Create SVL if missing
                    svl = self.env['stock.valuation.layer'].search([('stock_move_id', '=', move.id)], limit=1)
                    if not svl:
                        _logger.info("[tqt] No SVL for move %s, creating...", move.id)
                        if move._is_in():
                            move.with_context(force_valuation=True)._create_in_svl()
                        elif move._is_out():
                            move.with_context(force_valuation=True)._create_out_svl()
                        else:
                            move.with_context(force_valuation=True)._create_valuation_layers()

                    # Create accounting entries (idempotent in Odoo)
                    move.with_context(force_valuation=True)._account_entry_move()
                except Exception as e:
                    _logger.warning("[tqt] Rebuild valuation failed for move %s: %s", move.id, e)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.id if len(self) == 1 else False,
            'view_mode': 'form',
            'target': 'current',
        }
