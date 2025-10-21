# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class BuzWarrantyContract(models.Model):
    _name = 'buz.warranty.contract'
    _description = 'Warranty Contract'
    _order = 'name desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Contract Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'),
        copy=False
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id_for_domain)]"
    )
    product_tmpl_id_for_domain = fields.Many2one(
        related='template_id.product_tmpl_id',
        string='Template for Domain',
        store=False
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )
    template_id = fields.Many2one(
        'buz.warranty.template',
        string='Warranty Template',
        required=True
    )
    start_date = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today
    )
    end_date = fields.Date(
        string='End Date',
        compute='_compute_end_date',
        store=True,
        readonly=False
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', default='active', required=True)
    invoice_id = fields.Many2one(
        'account.move',
        string='Related Invoice',
        readonly=True,
        help='Invoice for extended warranty purchase'
    )
    note = fields.Text(
        string='Notes'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.depends('start_date', 'template_id.duration_months')
    def _compute_end_date(self):
        for contract in self:
            if contract.start_date and contract.template_id.duration_months:
                start_date = fields.Date.from_string(contract.start_date)
                end_date = start_date + timedelta(days=30*contract.template_id.duration_months)
                contract.end_date = end_date
            else:
                contract.end_date = contract.start_date

    @api.constrains('lot_id', 'start_date', 'end_date', 'state')
    def _check_overlapping_contracts(self):
        """Ensure no overlapping active contracts for the same lot"""
        for contract in self:
            if contract.state == 'active':
                overlapping_contracts = self.search([
                    ('id', '!=', contract.id),
                    ('lot_id', '=', contract.lot_id.id),
                    ('state', '=', 'active'),
                    ('start_date', '<=', contract.end_date),
                    ('end_date', '>=', contract.start_date),
                    ('company_id', '=', contract.company_id.id)
                ])
                if overlapping_contracts:
                    raise ValidationError(_(
                        "A warranty contract already exists for this lot/serial number "
                        "during the selected period (%s to %s). Please select a different period."
                    ) % (contract.start_date, contract.end_date))

    @api.constrains('lot_id', 'start_date')
    def _check_lot_delivered(self):
        """Ensure the lot has been delivered before creating a contract"""
        for contract in self:
            if contract.lot_id:
                # Check if the lot has been part of an outgoing stock move
                outgoing_moves = self.env['stock.move'].search([
                    ('lot_ids', 'in', [contract.lot_id.id]),
                    ('state', '=', 'done'),
                    ('picking_id.picking_type_id.code', '=', 'outgoing'),
                ])
                if not outgoing_moves:
                    raise ValidationError(_(
                        "Cannot create warranty contract for lot/serial '%s' "
                        "because it has not been delivered to a customer yet."
                    ) % contract.lot_id.name)

    def action_renew(self):
        """Create invoice for extended warranty renewal and extend the contract duration"""
        self.ensure_one()
        if self.template_id.coverage_type != 'extended':
            raise ValidationError(_("Only extended warranty contracts can be renewed."))
        if not self.template_id.sell_product_id:
            raise ValidationError(_("No sellable product defined for this warranty template."))

        # Create sales order and invoice
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.template_id.sell_product_id.id,
                    'product_uom_qty': 1,
                    'price_unit': self.template_id.sell_product_id.list_price,
                })
            ]
        })
        sale_order.action_confirm()
        
        # Confirm related invoice
        invoice = sale_order._create_invoices()
        invoice.action_post()
        
        # Update contract with invoice reference
        self.invoice_id = invoice.id
        
        # Extend contract by the template duration
        extension_months = self.template_id.duration_months
        new_end_date = fields.Date.from_string(self.end_date) + timedelta(days=30*extension_months)
        self.end_date = new_end_date

        return {
            'type': 'ir.actions.act_window',
            'name': _('Renewal Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.warranty.contract') or _('New')
        return super().create(vals)

    def reminder_cron_job(self):
        """Cron job to send warranty expiry reminders"""
        # Get the number of days before expiry from settings
        reminder_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'buz.reminder_days_before_expiry', default='7'
            )
        )
        
        # Find contracts that will expire within the specified number of days
        today = fields.Date.context_today(self)
        future_expiry_date = today + timedelta(days=reminder_days)
        
        contracts_to_remind = self.search([
            ('state', '=', 'active'),
            ('end_date', '<=', future_expiry_date),
            ('end_date', '>=', today),
            ('company_id', '=', self.env.company.id)
        ])
        
        # Get the email template
        email_template = self.env.ref(
            'buz_warranty_rma_management.email_template_warranty_expiry_reminder',
            raise_if_not_found=False
        )
        
        # Send reminder emails
        if email_template:
            for contract in contracts_to_remind:
                email_template.send_mail(contract.id, force_send=True)
        
        return True