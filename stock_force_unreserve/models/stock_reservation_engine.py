from odoo import models, fields, api

class StockReservationEngine(models.AbstractModel):
    _name = 'stock.reservation.engine'
    _description = 'Stock Reservation Force Engine'

    def force_reallocate(self, picking_id):
        picking = self.env['stock.picking'].browse(picking_id)
        if picking.state in ('done', 'cancel'):
            return {
                'status': 'failed',
                'message': 'Picking is already done or cancelled.'
            }

        moved_lines_info = []
        unreserved_from = set()
        remaining_shortage = 0.0

        reserved_field = 'reserved_uom_qty' if 'reserved_uom_qty' in self.env['stock.move.line']._fields else 'quantity'
        qty_done_field = 'quantity_done' if 'quantity_done' in self.env['stock.move']._fields else 'quantity'

        for move in picking.move_ids:
            if move.state not in ('assigned', 'partially_available', 'confirmed'):
                continue

            qty_done = getattr(move, qty_done_field)
            already_reserved = sum(move.move_line_ids.mapped(reserved_field))
            
            # Shortage = Demanded - Done - Already Reserved
            needed_qty = move.product_uom_qty - qty_done - already_reserved
            
            if needed_qty <= 0:
                continue

            domain = [
                ('product_id', '=', move.product_id.id),
                ('location_id', '=', move.location_id.id),
                (reserved_field, '>', 0),
                ('picking_id', '!=', picking.id),
                ('company_id', '=', picking.company_id.id),
                ('state', 'not in', ('done', 'cancel')),
            ]
            candidates = self.env['stock.move.line'].search(domain, order="create_date asc")
            
            for candidate in candidates:
                cand_reserved = getattr(candidate, reserved_field)
                if cand_reserved <= 0:
                    continue
                
                take_qty = min(cand_reserved, needed_qty)
                
                # Update candidate SML
                candidate.write({reserved_field: cand_reserved - take_qty})
                if candidate.move_id:
                    candidate.move_id._recompute_state() # Ensure move state updates
                
                needed_qty -= take_qty
                source_name = candidate.picking_id.name or str(candidate.picking_id.id)
                unreserved_from.add(source_name)
                moved_lines_info.append({
                    'product': move.product_id.display_name,
                    'qty': take_qty,
                    'from': source_name
                })
                
                # Log audit
                self.env['stock.reservation.log'].sudo().create({
                    'product_id': move.product_id.id,
                    'source_picking_id': candidate.picking_id.id,
                    'target_picking_id': picking.id,
                    'qty_moved': take_qty,
                    'user_id': self.env.user.id
                })
                
                if needed_qty <= 0:
                    break
                    
            remaining_shortage += needed_qty

        # Reassign current picking to reserve the stolen stock
        picking.action_assign()

        status = 'success'
        if remaining_shortage > 0 and len(moved_lines_info) > 0:
            status = 'partial'
        elif remaining_shortage > 0 and len(moved_lines_info) == 0:
            status = 'failed'

        return {
            'status': status,
            'moved_lines': moved_lines_info,
            'unreserved_from': list(unreserved_from),
            'remaining_shortage': remaining_shortage,
        }
