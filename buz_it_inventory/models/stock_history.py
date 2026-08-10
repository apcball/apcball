from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BuzItStockHistory(models.Model):
    _name = 'buz.it.stock.history'
    _description = 'IT Stock History'
    _order = 'move_date desc, create_date desc, id desc'

    move_type = fields.Selection([
        ('in', 'รับเข้า'),
        ('out', 'จ่ายออก'),
        ('adjust', 'ปรับยอด'),
    ], string='Type', required=True)
    inventory_item_id = fields.Many2one(
        'buz.it.inventory.item',
        string='Item',
        required=True,
        ondelete='restrict',
        index=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        required=True,
        ondelete='restrict',
    )
    qty = fields.Float(
        string='จำนวน',
        digits=(16, 0),
        required=True,
        help='การเปลี่ยนแปลงยอด (+ รับเข้า, - จ่ายออก, +/- ปรับยอด)',
    )
    move_date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    reference = fields.Char(string='Reference')
    note = fields.Text()
    request_id = fields.Many2one(
        'buz.it.issue.request',
        string='Issue Request',
        ondelete='set null',
        index=True,
    )
    request_line_id = fields.Many2one(
        'buz.it.issue.request.line',
        string='Issue Request Line',
        ondelete='set null',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='location_id.company_id',
        store=True,
        string='Company',
        index=True,
    )

    def write(self, vals):
        raise UserError(_(
            'Stock history is permanent and cannot be edited.'
        ))

    def unlink(self):
        raise UserError(_(
            'Stock history is permanent and cannot be deleted.'
        ))

    @api.constrains('inventory_item_id', 'location_id')
    def _check_company_consistency(self):
        for record in self:
            if (
                record.inventory_item_id.company_id
                and record.location_id.company_id
                and record.inventory_item_id.company_id
                != record.location_id.company_id
            ):
                raise ValidationError(_(
                    'The inventory item and stock location must belong to the same company.'
                ))
