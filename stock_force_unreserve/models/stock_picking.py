from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_force_unreserve_dialog(self):
        self.ensure_one()
        return {
            'name': 'Force Unreserve (Insight)',
            'type': 'ir.actions.client',
            'tag': 'stock_force_unreserve.force_unreserve_dialog',
            'target': 'new',
            'context': {
                'active_id': self.id,
            }
        }

    def action_execute_force_unreserve(self):
        self.ensure_one()
        return self.env['stock.reservation.engine'].force_reallocate(self.id)

    @api.model
    def get_reservation_insight_data(self, picking_id):
        picking = self.browse(picking_id)
        if not picking:
            return {}
            
        reserved_field = 'reserved_uom_qty' if 'reserved_uom_qty' in self.env['stock.move.line']._fields else 'quantity'
        qty_done_field = 'quantity_done' if 'quantity_done' in self.env['stock.move']._fields else 'quantity'

        insight_data = {
            'picking_name': picking.name,
            'lines': [],
            'competing_pickings': []
        }
        
        competing_pickings_set = set()

        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            qty_done = getattr(move, qty_done_field)
            already_reserved = sum(move.move_line_ids.mapped(reserved_field))
            needed_qty = move.product_uom_qty - qty_done - already_reserved
            
            status = 'available'
            if needed_qty > 0:
                if already_reserved > 0:
                    status = 'partial'
                else:
                    status = 'shortage'

            if needed_qty > 0:
                insight_data['lines'].append({
                    'product': move.product_id.display_name,
                    'demand': move.product_uom_qty,
                    'reserved': already_reserved,
                    'shortage': max(0, needed_qty),
                    'status': status
                })

                domain = [
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_id.id),
                    (reserved_field, '>', 0),
                    ('picking_id', '!=', picking.id),
                    ('company_id', '=', picking.company_id.id),
                    ('state', 'not in', ('done', 'cancel'))
                ]
                candidates = self.env['stock.move.line'].search(domain)
                for cand in candidates:
                    cand_reserved = getattr(cand, reserved_field)
                    competing_pickings_set.add(f"{cand.picking_id.name} -> {cand_reserved} units reserved ({cand.product_id.display_name})")

        insight_data['competing_pickings'] = list(competing_pickings_set)
        
        return insight_data
