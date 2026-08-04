from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


IT_GROUPS = (
    'buz_it_helpdesk.group_it_support_agent,'
    'buz_it_helpdesk.group_it_helpdesk_manager'
)
MANAGER_GROUP = 'buz_it_helpdesk.group_it_helpdesk_manager'


class HelpdeskTicketRepair(models.Model):
    _inherit = 'buz.helpdesk.ticket'

    requester_asset_ids = fields.Many2many(
        'buz.it.asset',
        compute='_compute_requester_asset_ids',
        string='Requester Assets',
        readonly=True,
    )
    asset_id = fields.Many2one(
        'buz.it.asset', string='Asset', ondelete='restrict', check_company=True,
        index=True, tracking=True,
    )
    asset_type_id = fields.Many2one(
        'buz.it.asset.type', string='Asset Type', related='asset_id.type_id',
        readonly=True,
    )
    asset_state_before_repair = fields.Selection([
        ('available', 'Available'),
        ('assigned', 'Assigned'),
        ('repair', 'Repair'),
        ('retired', 'Retired'),
        ('lost', 'Lost'),
    ], string='Asset State Before Repair', readonly=True, copy=False, groups=IT_GROUPS)
    repair_route = fields.Selection([
        ('internal', 'Internal IT Repair'),
        ('parts', 'Waiting for Parts / Upgrade'),
        ('external_it', 'External Repair by IT'),
        ('external_requester', 'External Repair by User / Department'),
        ('retire', 'Unrepairable / Retire'),
    ], string='Repair Route', tracking=True, groups=IT_GROUPS)
    repair_substate = fields.Selection([
        ('diagnosis', 'Awaiting Diagnosis'),
        ('internal_repair', 'Internal Repair'),
        ('waiting_parts', 'Waiting for Parts'),
        ('awaiting_user_send', 'Waiting for User / Department to Send'),
        ('sent_external', 'Sent for External Repair'),
        ('awaiting_return', 'Awaiting Return'),
        ('awaiting_verification', 'Awaiting IT Verification'),
        ('retire_pending', 'Retirement Approval Pending'),
        ('ready_close', 'Ready to Close'),
    ], string='Repair Progress', default='diagnosis', tracking=True, groups=IT_GROUPS)
    diagnosis = fields.Text(string='Inspection / Diagnosis', groups=IT_GROUPS)
    repair_instructions = fields.Text(string='Recommendations')
    repair_result = fields.Text(string='Repair Result')
    repair_outcome_id = fields.Many2one(
        'buz.it.asset.repair.outcome', string='Outcome', ondelete='restrict',
        tracking=True, copy=False,
        domain=[('active', '=', True)],
    )
    repair_outcome_behavior = fields.Selection(
        related='repair_outcome_id.behavior', readonly=True,
    )
    replacement_asset_id = fields.Many2one(
        'buz.it.asset', string='Replacement Asset', ondelete='restrict',
        check_company=True, copy=False, groups=IT_GROUPS,
    )
    repair_part_ids = fields.One2many(
        'buz.helpdesk.ticket.repair.part', 'ticket_id',
        string='Replacement Parts', copy=False, groups=IT_GROUPS,
    )
    parts_details = fields.Text(string='Parts / Upgrade Required', groups=IT_GROUPS)
    parts_responsible_id = fields.Many2one('res.users', string='Parts Owner', groups=IT_GROUPS)
    parts_order_date = fields.Date(string='Parts Ordered Date', groups=IT_GROUPS)
    parts_received_date = fields.Date(string='Parts Received Date', groups=IT_GROUPS)
    parts_reference = fields.Char(string='Parts Reference', groups=IT_GROUPS)
    external_vendor_id = fields.Many2one(
        'res.partner', string='External Repair Vendor', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        groups=IT_GROUPS,
    )
    external_technician_name = fields.Char(string='External Technician', groups=IT_GROUPS)
    external_sent_date = fields.Date(string='External Sent Date', groups=IT_GROUPS)
    external_expected_return_date = fields.Date(string='Expected Return Date', groups=IT_GROUPS)
    external_return_date = fields.Date(string='Actual Return Date', groups=IT_GROUPS)
    external_reference = fields.Char(string='External Repair Reference', groups=IT_GROUPS)
    external_quote = fields.Monetary(string='Quote', currency_field='currency_id', groups=IT_GROUPS)
    external_cost = fields.Monetary(string='External Repair Cost', currency_field='currency_id', groups=IT_GROUPS)
    external_warranty = fields.Char(string='Repair Warranty', groups=IT_GROUPS)
    external_test_result = fields.Text(string='IT Verification Result', groups=IT_GROUPS)
    requester_sent_date = fields.Date(string='User Sent Date', groups=IT_GROUPS)
    requester_vendor_name = fields.Char(string='User Repair Vendor', groups=IT_GROUPS)
    requester_expected_return_date = fields.Date(string='User Expected Return Date', groups=IT_GROUPS)
    requester_return_date = fields.Date(string='User Actual Return Date', groups=IT_GROUPS)
    requester_repair_result = fields.Text(string='User Repair Result', groups=IT_GROUPS)
    requester_cost = fields.Monetary(string='User Repair Cost', currency_field='currency_id', groups=IT_GROUPS)
    requester_warranty = fields.Char(string='User Repair Warranty', groups=IT_GROUPS)
    retire_reason = fields.Selection([
        ('beyond_repair', 'Beyond Repair'),
        ('obsolete', 'Obsolete / Unsupported'),
        ('no_parts', 'No Spare Parts'),
        ('uneconomical', 'Uneconomical to Repair'),
        ('other', 'Other'),
    ], string='Retirement Reason', groups=IT_GROUPS)
    retire_reason_detail = fields.Text(string='Retirement Details', groups=IT_GROUPS)
    retire_approved_by_id = fields.Many2one(
        'res.users', string='Retirement Approved By', readonly=True,
        groups=MANAGER_GROUP,
    )
    retire_approved_date = fields.Date(
        string='Retirement Approved Date', readonly=True,
        groups=MANAGER_GROUP,
    )
    retire_proposed = fields.Boolean(string='Retirement Proposed', readonly=True, copy=False, groups=IT_GROUPS)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True,
    )

    can_edit_repair_details = fields.Boolean(
        string='Can Edit Repair Details',
        compute='_compute_can_edit_repair_details',
    )
    has_legacy_repair_data = fields.Boolean(
        string='Has Legacy Repair Data',
        compute='_compute_has_legacy_repair_data', groups=IT_GROUPS,
    )

    @api.depends_context('uid')
    def _compute_can_edit_repair_details(self):
        can_edit = (
            self.env.user.has_group('buz_it_helpdesk.group_it_support_agent')
            or self.env.user.has_group('buz_it_helpdesk.group_it_helpdesk_manager')
        )
        for ticket in self:
            ticket.can_edit_repair_details = can_edit

    show_repair_process = fields.Boolean(
        string='Show Repair Process',
        compute='_compute_show_repair_process',
    )

    @api.depends('repair_route', 'repair_substate')
    def _compute_has_legacy_repair_data(self):
        for ticket in self:
            ticket.has_legacy_repair_data = bool(
                ticket.repair_route
                or ticket.repair_substate not in (False, 'diagnosis')
            )

    @api.depends(
        'repair_outcome_id', 'repair_result', 'repair_instructions', 'stage_id',
    )
    @api.depends_context('uid')
    def _compute_show_repair_process(self):
        is_it_user = self._is_support_agent()
        for ticket in self:
            ticket.show_repair_process = bool(
                is_it_user or ticket.repair_outcome_id or ticket.repair_result
                or ticket.repair_instructions
            )
    _repair_management_fields = {
        'diagnosis', 'repair_route', 'repair_substate', 'repair_instructions',
        'repair_result', 'parts_details', 'parts_responsible_id',
        'parts_order_date', 'parts_received_date', 'parts_reference',
        'external_vendor_id', 'external_technician_name', 'external_sent_date',
        'external_expected_return_date', 'external_return_date',
        'external_reference', 'external_quote', 'external_cost',
        'external_warranty', 'external_test_result', 'requester_sent_date',
        'requester_vendor_name', 'requester_expected_return_date',
        'requester_return_date', 'requester_repair_result', 'requester_cost',
        'requester_warranty', 'retire_reason', 'retire_reason_detail',
        'retire_approved_by_id', 'retire_approved_date', 'retire_proposed',
        'repair_outcome_id', 'replacement_asset_id', 'repair_part_ids',
    }

    def _check_repair_permission(self):
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can manage repair details.'))
        if not self._is_helpdesk_manager() and self.assigned_user_id != self.env.user:
            raise UserError(_('Only the assigned agent can manage this repair.'))

    @api.model
    def _normalize_taxonomy_name(self, value):
        return ' '.join((value or '').split()).casefold()

    @api.depends('requester_id', 'company_id', 'category_id', 'category_type_id')
    def _compute_requester_asset_ids(self):
        asset_model = self.env['buz.it.asset']
        asset_type_model = self.env['buz.it.asset.type']
        for ticket in self:
            ticket.requester_asset_ids = asset_model.browse()
            requester_employee = ticket.requester_id.employee_id
            if not ticket.category_id or not ticket.category_type_id or not requester_employee:
                continue
            type_name = self._normalize_taxonomy_name(ticket.category_type_id.name)
            matching_type_ids = asset_type_model.search([
                ('active', '=', True),
            ]).filtered(
                lambda asset_type: self._normalize_taxonomy_name(asset_type.name) == type_name
            ).ids
            if not matching_type_ids:
                continue
            ticket.requester_asset_ids = asset_model.search([
                ('company_id', '=', ticket.company_id.id),
                ('active', '=', True),
                ('state', 'not in', ['retired', 'lost']),
                ('assigned_employee_id', '=', requester_employee.id),
                ('type_id', 'in', matching_type_ids),
            ])

    @api.onchange('requester_id', 'category_id', 'category_type_id')
    def _onchange_requester_asset_domain(self):
        for ticket in self:
            if ticket.asset_id and ticket.asset_id not in ticket.requester_asset_ids:
                ticket.asset_id = False

    def _check_asset_selection(self, asset):
        if not asset:
            return
        if asset.company_id != self.company_id:
            raise ValidationError(_('The Asset must belong to the Ticket company.'))
        if asset.assigned_employee_id != self.requester_id.employee_id:
            raise ValidationError(_('The Asset must be assigned to the Ticket requester.'))
        if not self.category_id or not self.category_type_id:
            raise ValidationError(_('Select a Category and Type before selecting an Asset.'))
        matching_type_ids = self.env['buz.it.asset.type'].search([
            ('active', '=', True),
        ]).filtered(
            lambda asset_type: self._normalize_taxonomy_name(asset_type.name)
            == self._normalize_taxonomy_name(self.category_type_id.name)
        )
        if asset.type_id not in matching_type_ids:
            raise ValidationError(_('The Asset must match the selected Type.'))
        if asset.state in ('retired', 'lost'):
            raise ValidationError(_('Retired or lost Assets cannot be repaired.'))

    def _check_replacement_asset(self, replacement_asset):
        self.ensure_one()
        if not replacement_asset:
            return
        if replacement_asset == self.asset_id:
            raise ValidationError(_(
                'The Replacement Asset must be different from the repaired Asset.'
            ))
        if replacement_asset.company_id != self.company_id:
            raise ValidationError(_(
                'The Replacement Asset must belong to the Ticket company.'
            ))

    @api.constrains('asset_id', 'replacement_asset_id', 'company_id')
    def _check_replacement_asset_constraint(self):
        for ticket in self:
            ticket._check_replacement_asset(ticket.replacement_asset_id)

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_support_agent():
            for vals in vals_list:
                if self._repair_management_fields.intersection(vals):
                    raise UserError(_(
                        'Only IT Support Agents can set repair details.'
                    ))
        approval_fields = {
            'retire_proposed', 'retire_approved_by_id', 'retire_approved_date',
        }
        if not self.env.su and any(
            approval_fields.intersection(vals) for vals in vals_list
        ):
            raise UserError(_('Retirement approval fields are system-managed.'))
        records = super().create(vals_list)
        for ticket in records:
            if ticket.asset_id:
                ticket._check_asset_selection(ticket.asset_id)
            ticket._check_replacement_asset(ticket.replacement_asset_id)
        return records
    def write(self, vals):
        if self._is_support_agent() is False and self._repair_management_fields.intersection(vals):
            raise UserError(_('Only IT Support Agents can edit repair details.'))
        if 'repair_outcome_id' in vals:
            outcome = self.env['buz.it.asset.repair.outcome'].browse(
                vals['repair_outcome_id'],
            ).exists()
            behavior = outcome.behavior if outcome else False
            if behavior != 'asset_replaced':
                vals['replacement_asset_id'] = False
            if behavior != 'parts_replaced':
                self.mapped('repair_part_ids').unlink()
        if 'asset_id' in vals:
            for ticket in self:
                if ticket.is_closed_stage:
                    raise UserError(_('The Asset cannot be changed after the Ticket is closed.'))
                asset = self.env['buz.it.asset'].browse(vals['asset_id']).exists()
                ticket._check_asset_selection(asset)
        if 'replacement_asset_id' in vals:
            replacement = self.env['buz.it.asset'].browse(
                vals['replacement_asset_id'],
            ).exists()
            for ticket in self:
                ticket._check_replacement_asset(replacement)
        approval_fields = {
            'retire_proposed', 'retire_approved_by_id', 'retire_approved_date',
        }
        if approval_fields.intersection(vals) and not self.env.su:
            raise UserError(_('Retirement approval fields are system-managed.'))
        if (
            {'repair_outcome_id', 'retire_reason', 'retire_reason_detail'}.intersection(vals)
            and not self.env.su
        ):
            self.sudo().write({
                'retire_proposed': False,
                'retire_approved_by_id': False,
                'retire_approved_date': False,
            })
        for ticket in self:
            if (
                ticket.is_closed_stage
                and self._repair_management_fields.intersection(vals)
            ):
                raise UserError(_(
                    'Closed repair details cannot be changed. Create a Follow-up Ticket.'
                ))
        return super().write(vals)

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'diagnosis': False,
            'repair_result': False,
            'repair_outcome_id': False,
            'repair_instructions': False,
            'replacement_asset_id': False,
            'repair_part_ids': False,
            'retire_reason': False,
            'retire_reason_detail': False,
            'retire_proposed': False,
            'retire_approved_by_id': False,
            'retire_approved_date': False,
            'repair_route': False,
            'repair_substate': 'diagnosis',
            'asset_state_before_repair': False,
        })
        return super().copy(default)

    def action_propose_retirement(self):
        self.ensure_one()
        self._check_repair_permission()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Retirement can be proposed only for an In Progress Ticket.'))
        if not self.asset_id or self.repair_outcome_behavior != 'retired':
            raise UserError(_('Select an Asset and the Retired outcome first.'))
        if not self.retire_reason:
            raise UserError(_('Select the reason for retirement.'))
        if self.retire_proposed:
            raise UserError(_('Asset retirement has already been proposed.'))
        managers = self.env['res.users'].search([
            ('active', '=', True),
            ('groups_id', 'in', self.env.ref(
                'buz_it_helpdesk.group_it_helpdesk_manager'
            ).id),
        ])
        for manager in managers:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=manager.id,
                summary=_('Approve Asset Retirement'),
                note=_(
                    'Review retirement proposal for %(ticket)s.',
                    ticket=self.display_name,
                ),
            )
        self.sudo().write({
            'retire_proposed': True,
            'retire_approved_by_id': False,
            'retire_approved_date': False,
        })
        self.message_post(
            body=_('Asset retirement has been proposed for Manager approval.')
        )
        return True

    def action_approve_retirement(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only a Helpdesk Manager can approve retirement.'))
        if (
            not self.asset_id
            or self.repair_outcome_behavior != 'retired'
            or not self.retire_proposed
        ):
            raise UserError(_('This Ticket is not awaiting retirement approval.'))
        self.sudo().write({
            'retire_approved_by_id': self.env.user.id,
            'retire_approved_date': fields.Date.context_today(self),
        })
        return True

    def action_reject_retirement(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only a Helpdesk Manager can reject retirement.'))
        if not self.retire_proposed or self.retire_approved_by_id:
            raise UserError(_('This Ticket is not awaiting retirement approval.'))
        self.sudo().write({
            'retire_proposed': False,
            'retire_approved_by_id': False,
            'retire_approved_date': False,
        })
        self.message_post(body=_('Asset retirement proposal was rejected.'))
        return True

    def _validate_simple_repair_close(self):
        self.ensure_one()
        if not self.asset_id:
            return
        self._check_repair_permission()
        if not self.repair_result:
            raise UserError(_('Enter the repair result before closing this Ticket.'))
        if not self.repair_outcome_id:
            raise UserError(_('Select the repair outcome before closing this Ticket.'))
        if self.repair_outcome_behavior == 'parts_replaced' and not self.repair_part_ids:
            raise UserError(_('Add at least one replacement part before closing this Ticket.'))
        if self.repair_outcome_behavior != 'parts_replaced' and self.repair_part_ids:
            raise UserError(_(
                'Replacement parts are allowed only for the Parts Replaced outcome.'
            ))
        if self.repair_outcome_behavior == 'asset_replaced':
            if not self.replacement_asset_id:
                raise UserError(_('Select the Replacement Asset before closing this Ticket.'))
            self._check_replacement_asset(self.replacement_asset_id)
        elif self.replacement_asset_id:
            raise UserError(_(
                'Replacement Asset is allowed only for the Asset Replaced outcome.'
            ))
        if self.repair_outcome_behavior == 'retired':
            if not self.retire_reason:
                raise UserError(_('Select the reason for retirement.'))
            if not self.retire_proposed or not self.sudo().retire_approved_by_id:
                raise UserError(_(
                    'Manager approval is required before retiring the Asset.'
                ))

    def action_close_ticket(self):
        self.ensure_one()
        self._validate_simple_repair_close()
        result = super().action_close_ticket()
        if self.asset_id:
            self.env['buz.it.asset.maintenance']._create_from_ticket(self)
            if self.repair_outcome_behavior == 'retired':
                self.asset_id.write({'state': 'retired'})
        return result


class HelpdeskTicketRepairPart(models.Model):
    _name = 'buz.helpdesk.ticket.repair.part'
    _description = 'Helpdesk Ticket Replacement Part'
    _order = 'id'

    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket', required=True, ondelete='cascade',
        check_company=True, index=True,
    )
    company_id = fields.Many2one(
        related='ticket_id.company_id', store=True, readonly=True,
    )
    name = fields.Char(string='Part Name', required=True)
    quantity = fields.Float(default=1.0, required=True)
    old_serial = fields.Char(string='Old Serial Number')
    new_serial = fields.Char(string='New Serial Number')
    unit_price = fields.Monetary(
        string='Unit Price', currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='ticket_id.currency_id', store=True, readonly=True,
    )
    notes = fields.Text()

    @api.constrains('quantity', 'unit_price')
    def _check_values(self):
        for part in self:
            if part.quantity <= 0:
                raise ValidationError(_('Part quantity must be greater than zero.'))
            if part.unit_price < 0:
                raise ValidationError(_('Part price cannot be negative.'))

    def _check_ticket_edit_permission(self, tickets=None):
        for ticket in tickets or self.mapped('ticket_id'):
            ticket._check_repair_permission()
            if ticket.is_closed_stage:
                raise UserError(_('Replacement parts cannot be changed after closing the Ticket.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(not vals.get('ticket_id') for vals in vals_list):
            raise ValidationError(_(
                'A valid Ticket is required for every replacement part.'
            ))
        ticket_ids = {vals['ticket_id'] for vals in vals_list}
        tickets = self.env['buz.helpdesk.ticket'].browse(ticket_ids).exists()
        if len(tickets) != len(ticket_ids):
            raise ValidationError(_(
                'A valid Ticket is required for every replacement part.'
            ))
        self._check_ticket_edit_permission(tickets)
        return super().create(vals_list)

    def write(self, vals):
        self._check_ticket_edit_permission()
        if vals.get('ticket_id'):
            ticket = self.env['buz.helpdesk.ticket'].browse(
                vals['ticket_id']
            ).exists()
            if not ticket:
                raise ValidationError(_('A valid Ticket is required.'))
            self._check_ticket_edit_permission(ticket)
        return super().write(vals)
    def unlink(self):
        self._check_ticket_edit_permission()
        return super().unlink()

class ITAssetMaintenance(models.Model):
    _inherit = 'buz.it.asset.maintenance'

    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket', string='Source Ticket', ondelete='restrict',
        index=True, copy=False, groups=IT_GROUPS,
    )
    asset_type_id = fields.Many2one(related='asset_id.type_id', readonly=True)
    repair_route = fields.Selection(related='ticket_id.repair_route', readonly=True, groups=IT_GROUPS)
    diagnosis = fields.Text(related='ticket_id.diagnosis', readonly=True, groups=IT_GROUPS)
    repair_result = fields.Text(related='ticket_id.repair_result', readonly=True)
    repair_outcome_id = fields.Selection([
        ('repaired', 'Repaired'),
        ('parts_replaced', 'Parts Replaced'),
        ('asset_replaced', 'Asset Replaced'),
        ('retired', 'Retired'),
        ('no_repair', 'No Repair'),
    ], string='Outcome', readonly=True)
    recommendations = fields.Text(readonly=True)
    performed_by_id = fields.Many2one(
        'res.users', string='Performed By', readonly=True, groups=IT_GROUPS,
    )
    replacement_asset_id = fields.Many2one(
        'buz.it.asset', string='Replacement Asset', readonly=True,
        ondelete='restrict', check_company=True, groups=IT_GROUPS,
    )
    repair_part_ids = fields.One2many(
        'buz.it.asset.maintenance.part', 'maintenance_id',
        string='Replacement Parts', readonly=True, groups=IT_GROUPS,
    )
    parts_details = fields.Text(related='ticket_id.parts_details', readonly=True, groups=IT_GROUPS)
    parts_reference = fields.Char(related='ticket_id.parts_reference', readonly=True, groups=IT_GROUPS)
    parts_order_date = fields.Date(related='ticket_id.parts_order_date', readonly=True, groups=IT_GROUPS)
    parts_received_date = fields.Date(related='ticket_id.parts_received_date', readonly=True, groups=IT_GROUPS)
    external_sent_date = fields.Date(related='ticket_id.external_sent_date', readonly=True, groups=IT_GROUPS)
    external_expected_return_date = fields.Date(
        related='ticket_id.external_expected_return_date',
        readonly=True, groups=IT_GROUPS,
    )
    external_return_date = fields.Date(related='ticket_id.external_return_date', readonly=True, groups=IT_GROUPS)
    external_reference = fields.Char(related='ticket_id.external_reference', readonly=True, groups=IT_GROUPS)
    external_quote = fields.Monetary(related='ticket_id.external_quote', readonly=True, groups=IT_GROUPS)
    external_cost = fields.Monetary(related='ticket_id.external_cost', readonly=True, groups=IT_GROUPS)
    external_warranty = fields.Char(related='ticket_id.external_warranty', readonly=True, groups=IT_GROUPS)
    requester_sent_date = fields.Date(related='ticket_id.requester_sent_date', readonly=True, groups=IT_GROUPS)
    requester_vendor_name = fields.Char(related='ticket_id.requester_vendor_name', readonly=True, groups=IT_GROUPS)
    requester_return_date = fields.Date(related='ticket_id.requester_return_date', readonly=True, groups=IT_GROUPS)
    requester_cost = fields.Monetary(related='ticket_id.requester_cost', readonly=True, groups=IT_GROUPS)
    requester_warranty = fields.Char(related='ticket_id.requester_warranty', readonly=True, groups=IT_GROUPS)
    retirement_reason = fields.Selection(
        related='ticket_id.retire_reason', readonly=True, groups=IT_GROUPS,
    )
    retirement_details = fields.Text(
        related='ticket_id.retire_reason_detail', readonly=True,
        groups=IT_GROUPS,
    )

    _sql_constraints = [
        ('ticket_maintenance_uniq', 'unique(ticket_id)',
         'A Ticket can create only one maintenance history.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('buz_repair_history_from_ticket'):
            raise UserError(_('Maintenance history can only be created from a closed Ticket.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Maintenance history is read-only. Update the source Ticket instead.'))

    def unlink(self):
        raise UserError(_('Maintenance history cannot be deleted.'))

    @api.model
    def _create_from_ticket(self, ticket):
        ticket.ensure_one()
        existing = self.sudo().search([('ticket_id', '=', ticket.id)], limit=1)
        if existing:
            return existing
        if not ticket.is_closed_stage or not ticket.asset_id:
            raise UserError(_(
                'Maintenance history can only be created from a closed Ticket with an Asset.'
            ))
        operator = ticket.assigned_user_id or self.env.user
        employee = operator.employee_id
        vals = {
            'ticket_id': ticket.id,
            'asset_id': ticket.asset_id.id,
            'sent_date': (
                ticket.create_ticket_date or fields.Date.context_today(ticket)
            ),
            'symptom': ticket.description or ticket.subject,
            'state': 'done',
            'completed_date': (
                ticket.closed_ticket_date or fields.Date.context_today(ticket)
            ),
            'technician_employee_id': (
                employee.id
                if employee and employee.company_id == ticket.company_id
                else False
            ),
            'performed_by_id': operator.id,
            'repair_outcome_id': ticket.repair_outcome_id.code if ticket.repair_outcome_id else False,
            'recommendations': ticket.repair_instructions,
            'replacement_asset_id': ticket.replacement_asset_id.id,
            'external_technician_name': (
                ticket.external_technician_name
                or ticket.requester_vendor_name
            ),
            'vendor_id': ticket.external_vendor_id.id,
            'cost': ticket.external_cost or ticket.requester_cost,
            'notes': ticket.repair_result,
            'attachment_ids': [
                fields.Command.set(ticket.attachment_ids.ids)
            ],
            'repair_part_ids': [
                fields.Command.create({
                    'name': part.name,
                    'quantity': part.quantity,
                    'old_serial': part.old_serial,
                    'new_serial': part.new_serial,
                    'unit_price': part.unit_price,
                    'notes': part.notes,
                })
                for part in ticket.repair_part_ids
            ],
        }
        return self.with_context(
            buz_repair_history_from_ticket=True,
        ).sudo().create(vals)

class ITAssetMaintenancePart(models.Model):
    _name = 'buz.it.asset.maintenance.part'
    _description = 'IT Asset Maintenance Replacement Part'
    _order = 'id'

    maintenance_id = fields.Many2one(
        'buz.it.asset.maintenance', required=True, ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='maintenance_id.company_id', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        related='maintenance_id.currency_id', store=True, readonly=True,
    )
    name = fields.Char(string='Part Name', required=True, readonly=True)
    quantity = fields.Float(required=True, readonly=True)
    old_serial = fields.Char(string='Old Serial Number', readonly=True)
    new_serial = fields.Char(string='New Serial Number', readonly=True)
    unit_price = fields.Monetary(
        string='Unit Price', currency_field='currency_id', readonly=True,
    )
    notes = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('buz_repair_history_from_ticket'):
            raise UserError(_(
                'Maintenance parts can only be created from a closed Ticket.'
            ))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Maintenance history is read-only.'))

    def unlink(self):
        raise UserError(_('Maintenance history cannot be deleted.'))
