from collections import defaultdict

from odoo import fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

from .show_loan import operation_marker


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    show_loan_id = fields.Many2one('buz.show.loan', index=True, copy=True, check_company=True)
    show_loan_role = fields.Selection(
        [('loan', 'Show Loan'), ('return', 'Show Return')], copy=True, index=True,
    )

    def _action_done(self):
        returns = self.filtered(lambda picking: picking.show_loan_role == 'return')
        for loan_id in sorted(set(returns.mapped('show_loan_id').ids)):
            self.env.cr.execute('SELECT id FROM buz_show_loan WHERE id = %s FOR UPDATE', [loan_id])
        if returns:
            self.env.invalidate_all()
        actual_by_line = defaultdict(float)
        for picking in returns:
            loan = picking.show_loan_id
            if (not loan or picking.company_id != loan.company_id
                    or picking.location_id != loan.location_dest_id
                    or picking.location_dest_id.complete_name != 'FG40/Stock'
                    or 'RBG' not in operation_marker(picking.picking_type_id)
                    or picking.origin != loan.picking_id.name):
                raise ValidationError(_('This RBG Transfer does not match its show loan.'))
            for move in picking.move_ids.filtered(lambda move: move.state != 'cancel'):
                line = move.show_loan_line_id
                if not line or line.loan_id != loan or move.product_id != line.product_id:
                    raise ValidationError(_('Every RBG product must match a line of its show loan.'))
                actual_by_line[line] += move.product_uom._compute_quantity(move.quantity, line.uom_id)
        for line, actual in actual_by_line.items():
            if float_compare(actual, line.qty_issued - line.qty_returned,
                             precision_rounding=line.uom_id.rounding) > 0:
                raise ValidationError(_('RBG quantity exceeds the quantity issued but not yet returned.'))
        return super()._action_done()


class StockMove(models.Model):
    _inherit = 'stock.move'

    show_loan_line_id = fields.Many2one('buz.show.loan.line', index=True, copy=True)
