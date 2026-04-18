from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_bulk_cancel(self):
        success_count = 0
        failed_count = 0

        for picking in self:
            try:
                with self.env.cr.savepoint():
                    if picking.state == 'done':
                        raise ValueError(_("Cannot cancel picking %s because it is already done.") % picking.name)
                    
                    if any(move.state == 'done' for move in picking.move_ids):
                        raise ValueError(_("Cannot cancel picking %s because some moves are already done.") % picking.name)

                    if picking.state in ['assigned', 'confirmed']:
                        if hasattr(picking, 'do_unreserve'):
                            picking.do_unreserve()
                        elif hasattr(picking, '_action_unreserve'):
                            picking._action_unreserve()
                    
                    picking.action_cancel()
                    success_count += 1
                    
            except Exception as e:
                failed_count += 1
                # If an error happens inside savepoint, it rolls back. We need to create the log outside the failed savepoint.
                try:
                    with self.env.cr.savepoint():
                        self.env['stock.picking.bulk.cancel.log'].create({
                            'picking_id': picking.id,
                            'picking_name': picking.name,
                            'status': 'failed',
                            'message': str(e),
                        })
                except Exception as inner_e:
                    _logger.error("Failed to create log for %s: %s", picking.name, str(inner_e))

        if failed_count == 0:
            message = _("Successfully cancelled %s pickings.") % success_count
            msg_type = 'success'
        else:
            message = _("Successfully cancelled %s pickings. Failed to cancel %s pickings. Check logs for details.") % (success_count, failed_count)
            msg_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Cancel Result'),
                'message': message,
                'type': msg_type,
                'sticky': False,
            }
        }
