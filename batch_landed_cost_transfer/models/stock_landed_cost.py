from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    batch_id = fields.Many2one(
        'stock.picking.batch', 
        string='Batch Transfer',
        help='Batch Transfer to populate picking lines from.'
    )

    @api.onchange('batch_id')
    def _onchange_batch_id(self):
        if self.batch_id:
            # Load all stock.picking in that batch
            # Filter only: state = 'done', picking_type_id.code = 'incoming'
            valid_pickings = self.batch_id.picking_ids.filtered(
                lambda p: p.state == 'done' and p.picking_type_id.code == 'incoming'
            )
            
            # Auto assign all filtered pickings to picking_ids
            # Using (6, 0, ids) command to replace existing list
            self.picking_ids = [(6, 0, valid_pickings.ids)]

    # @api.constrains('batch_id', 'picking_ids')
    # def _check_batch_consistency(self):
    #     for cost in self:
    #         if cost.batch_id and cost.picking_ids:
    #             # 4.1 Batch Consistency: All picking_ids must belong to the same batch
    #             # We check if any picking in the list does NOT match the selected batch_id
    #             invalid_pickings = cost.picking_ids.filtered(lambda p: p.batch_id != cost.batch_id)
    #             if invalid_pickings:
    #                 raise ValidationError(_("Consistency Error: When a Batch Transfer is selected, all Transfers must belong to that Batch."))

    # @api.constrains('batch_id', 'state')
    # def _check_batch_reuse(self):
    #     for cost in self:
    #         if cost.batch_id:
    #             # 4.2 Prevent Batch Reuse
    #             # If a Batch Transfer was already used in a Posted Landed Cost
    #             duplicate_costs = self.search([
    #                 ('batch_id', '=', cost.batch_id.id),
    #                 ('id', '!=', cost.id),
    #                 ('state', '=', 'done')
    #             ])
    #             if duplicate_costs:
    #                 raise ValidationError(_("This Batch Transfer has already been used in another posted Landed Cost."))
