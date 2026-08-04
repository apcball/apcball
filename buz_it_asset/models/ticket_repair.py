from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HelpdeskTicketRepair(models.Model):
    _inherit = 'buz.helpdesk.ticket'

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
    ], string='Asset State Before Repair', readonly=True, copy=False)
    repair_route = fields.Selection([
        ('internal', 'Internal IT Repair'),
        ('parts', 'Waiting for Parts / Upgrade'),
        ('external_it', 'External Repair by IT'),
        ('external_requester', 'External Repair by User / Department'),
        ('retire', 'Unrepairable / Retire'),
    ], string='Repair Route', tracking=True)
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
    ], string='Repair Progress', default='diagnosis', tracking=True)
    diagnosis = fields.Text(string='Inspection / Diagnosis')
    repair_instructions = fields.Text(string='Instructions to User / Department')
    repair_result = fields.Text(string='Repair Result')
    parts_details = fields.Text(string='Parts / Upgrade Required')
    parts_responsible_id = fields.Many2one('res.users', string='Parts Owner')
    parts_order_date = fields.Date(string='Parts Ordered Date')
    parts_received_date = fields.Date(string='Parts Received Date')
    parts_reference = fields.Char(string='Parts Reference')
    external_vendor_id = fields.Many2one(
        'res.partner', string='External Repair Vendor', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    external_technician_name = fields.Char(string='External Technician')
    external_sent_date = fields.Date(string='External Sent Date')
    external_expected_return_date = fields.Date(string='Expected Return Date')
    external_return_date = fields.Date(string='Actual Return Date')
    external_reference = fields.Char(string='External Repair Reference')
    external_quote = fields.Monetary(string='Quote', currency_field='currency_id')
    external_cost = fields.Monetary(string='External Repair Cost', currency_field='currency_id')
    external_warranty = fields.Char(string='Repair Warranty')
    external_test_result = fields.Text(string='IT Verification Result')
    requester_sent_date = fields.Date(string='User Sent Date')
    requester_vendor_name = fields.Char(string='User Repair Vendor')
    requester_expected_return_date = fields.Date(string='User Expected Return Date')
    requester_return_date = fields.Date(string='User Actual Return Date')
    requester_repair_result = fields.Text(string='User Repair Result')
    requester_cost = fields.Monetary(string='User Repair Cost', currency_field='currency_id')
    requester_warranty = fields.Char(string='User Repair Warranty')
    retire_reason = fields.Selection([
        ('beyond_repair', 'Beyond Repair'),
        ('obsolete', 'Obsolete / Unsupported'),
        ('no_parts', 'No Spare Parts'),
        ('uneconomical', 'Uneconomical to Repair'),
        ('other', 'Other'),
    ], string='Retirement Reason')
    retire_reason_detail = fields.Text(string='Retirement Details')
    retire_approved_by_id = fields.Many2one('res.users', string='Retirement Approved By', readonly=True)
    retire_approved_date = fields.Date(string='Retirement Approved Date', readonly=True)
    retire_proposed = fields.Boolean(string='Retirement Proposed', readonly=True, copy=False)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True,
    )

    can_edit_repair_details = fields.Boolean(
        string='Can Edit Repair Details',
        compute='_compute_can_edit_repair_details',
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

    @api.depends('asset_id', 'stage_id')
    @api.depends_context('uid')
    def _compute_show_repair_process(self):
        in_progress_stage = self.env.ref('buz_it_helpdesk.stage_in_progress')
        is_it_user = self._is_support_agent()
        for ticket in self:
            ticket.show_repair_process = bool(
                ticket.asset_id
                and (
                    is_it_user
                    or ticket.stage_id.sequence >= in_progress_stage.sequence
                )
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
            'retire_approved_by_id', 'retire_approved_date',
        'retire_proposed',
    }

    def _check_repair_permission(self):
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can manage repair details.'))
        if not self._is_helpdesk_manager() and self.assigned_user_id != self.env.user:
            raise UserError(_('Only the assigned agent can manage this repair.'))

    def _check_asset_selection(self, asset):
        if not asset:
            return
        if asset.company_id != self.company_id:
            raise ValidationError(_('The Asset must belong to the Ticket company.'))
        if not self._is_support_agent() and asset.assigned_employee_id.user_id != self.requester_id:
            raise ValidationError(_('Users can only select an Asset assigned to themselves.'))
        if asset.state in ('retired', 'lost'):
            raise ValidationError(_('Retired or lost Assets cannot be repaired.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for ticket in records:
            if ticket.asset_id:
                ticket._check_asset_selection(ticket.asset_id)
        return records

    def write(self, vals):
        if self.env.context.get('buz_repair_transition'):
            if self._repair_management_fields.intersection(vals) or 'asset_id' in vals:
                for ticket in self:
                    ticket._check_repair_permission()
                    if 'asset_id' in vals:
                        asset = self.env['buz.it.asset'].browse(vals['asset_id']).exists()
                        ticket._check_asset_selection(asset)
            return super().write(vals)
        if self.env.context.get('buz_user_repair_report'):
            allowed = {
                'requester_sent_date', 'requester_vendor_name',
                'requester_expected_return_date', 'requester_return_date',
                'requester_repair_result', 'requester_cost',
                'requester_warranty', 'repair_substate', 'attachment_ids',
            }
            if not set(vals).issubset(allowed):
                raise UserError(_('Only the external repair report fields can be updated.'))
            for ticket in self:
                if ticket.requester_id != self.env.user:
                    raise UserError(_('Only the requester can submit this report.'))
                expected = {
                    'awaiting_user_send': 'awaiting_return',
                    'awaiting_return': 'awaiting_verification',
                }.get(ticket.repair_substate)
                if vals.get('repair_substate') and vals['repair_substate'] != expected:
                    raise UserError(_('The external repair report is not valid for the current step.'))
            return super().write(vals)
        if self._is_support_agent() is False and self._repair_management_fields.intersection(vals):
            raise UserError(_('Only IT Support Agents can edit repair details.'))
        if 'asset_id' in vals:
            for ticket in self:
                if ticket.repair_substate != 'diagnosis' or ticket.is_closed_stage:
                    raise UserError(_('The Asset cannot be changed after repair processing has started.'))
                asset = self.env['buz.it.asset'].browse(vals['asset_id']).exists()
                ticket._check_asset_selection(asset)
        if self._is_helpdesk_manager() is False:
            for ticket in self:
                if ticket.is_closed_stage and self._repair_management_fields.intersection(vals):
                    raise UserError(_('Closed repair details cannot be changed.'))
        return super().write(vals)

    def _ensure_route_owner(self):
        self.ensure_one()
        self._check_repair_permission()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Repair processing is available only for In Progress tickets.'))
        if not self.asset_id:
            raise UserError(_('Select an Asset before starting repair processing.'))

    def action_confirm_repair_route(self):
        self.ensure_one()
        self._ensure_route_owner()
        if not self.diagnosis:
            raise UserError(_('Enter the inspection / diagnosis first.'))
        if not self.repair_route:
            raise UserError(_('Select a repair route first.'))
        if self.repair_route and self.repair_substate != 'diagnosis':
            raise UserError(_('Repair processing has already started for this Ticket.'))
        active = self.search([
            ('id', '!=', self.id), ('asset_id', '=', self.asset_id.id),
            ('stage_id', '!=', self.env.ref('buz_it_helpdesk.stage_closed').id),
            ('repair_substate', '!=', 'diagnosis'),
        ], limit=1)
        if active:
            raise UserError(_('Another active repair Ticket already uses this Asset.'))
        substate = {
            'internal': 'internal_repair',
            'parts': 'waiting_parts',
            'external_it': 'sent_external',
            'external_requester': 'awaiting_user_send',
            'retire': 'retire_pending',
        }[self.repair_route]
        if self.repair_route == 'external_it' and not (
                self.external_vendor_id and self.external_sent_date
                and self.external_expected_return_date):
            raise UserError(_('Enter the vendor, sent date, and expected return date.'))
        if self.repair_route == 'parts' and not self.parts_details:
            raise UserError(_('Enter the required parts or upgrade details.'))
        if self.repair_route == 'retire' and not self.retire_reason:
            raise UserError(_('Select the reason for retirement.'))
        values = {
            'repair_substate': substate,
            'retire_proposed': False,
        }
        if not self.asset_state_before_repair:
            values['asset_state_before_repair'] = self.asset_id.state
        self.with_context(buz_repair_transition=True).write(values)
        self.asset_id.with_context(buz_repair_transition=True).write({'state': 'repair'})
        if self.repair_route == 'external_it':
            self.message_post(body=_('Asset sent to external repair vendor.'))
        return True

    def action_mark_parts_received(self):
        self.ensure_one()
        self._ensure_route_owner()
        if self.repair_route != 'parts' or self.repair_substate != 'waiting_parts':
            raise UserError(_('This Ticket is not waiting for parts.'))
        if not self.parts_received_date:
            raise UserError(_('Enter the parts received date.'))
        self.with_context(buz_repair_transition=True).write({'repair_substate': 'internal_repair'})
        return True

    def action_mark_external_received(self):
        self.ensure_one()
        self._ensure_route_owner()
        if self.repair_route != 'external_it' or self.repair_substate != 'sent_external':
            raise UserError(_('This Ticket is not awaiting an external repair return.'))
        if not self.external_return_date:
            raise UserError(_('Enter the actual return date.'))
        self.with_context(buz_repair_transition=True).write({'repair_substate': 'awaiting_verification'})
        return True

    def action_verify_repair(self):
        self.ensure_one()
        self._ensure_route_owner()
        if self.repair_substate != 'awaiting_verification':
            raise UserError(_('This Ticket is not awaiting IT verification.'))
        if not self.external_test_result:
            raise UserError(_('Enter the IT verification result.'))
        if not self.repair_result:
            self.with_context(buz_repair_transition=True).write({
                'repair_result': self.requester_repair_result,
            })
        if not self.repair_result:
            raise UserError(_('Enter the repair result before verification.'))
        self.with_context(buz_repair_transition=True).write({'repair_substate': 'ready_close'})
        return True

    def action_mark_ready_close(self):
        self.ensure_one()
        self._ensure_route_owner()
        if self.repair_route not in ('internal', 'parts'):
            raise UserError(_('Use the verification action for external repairs.'))
        if self.repair_route == 'parts' and not self.parts_received_date:
            raise UserError(_('Enter the parts received date.'))
        if not self.repair_result:
            raise UserError(_('Enter the repair result.'))
        self.with_context(buz_repair_transition=True).write({'repair_substate': 'ready_close'})
        return True

    def action_propose_retirement(self):
        self.ensure_one()
        self._ensure_route_owner()
        if self.repair_route != 'retire' or self.repair_substate != 'retire_pending':
            raise UserError(_('This Ticket is not awaiting retirement approval.'))
        if not self.retire_reason:
            raise UserError(_('Select the reason for retirement.'))
        managers = self.env['res.users'].search([
            ('active', '=', True),
            ('groups_id', 'in', self.env.ref('buz_it_helpdesk.group_it_helpdesk_manager').id),
        ]) - self.env.user
        for manager in managers:
            self.activity_schedule(
                'mail.mail_activity_data_todo', user_id=manager.id,
                summary=_('Approve Asset Retirement'),
                note=_('Review retirement proposal for %(ticket)s.', ticket=self.display_name),
            )
        self.message_post(body=_('Asset retirement has been proposed for Manager approval.'))
        self.with_context(buz_repair_transition=True).write({'retire_proposed': True})
        return True

    def action_approve_retirement(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only a Helpdesk Manager can approve retirement.'))
        if (self.repair_route != 'retire' or self.repair_substate != 'retire_pending'
                or not self.retire_proposed):
            raise UserError(_('This Ticket is not awaiting retirement approval.'))
        self.with_context(buz_repair_transition=True).write({
            'retire_approved_by_id': self.env.user.id,
            'retire_approved_date': fields.Date.context_today(self),
            'repair_substate': 'ready_close',
        })
        return True

    def action_reject_retirement(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only a Helpdesk Manager can reject retirement.'))
        if (self.repair_route != 'retire' or self.repair_substate != 'retire_pending'
                or not self.retire_proposed):
            raise UserError(_('This Ticket is not awaiting retirement approval.'))
        self.with_context(buz_repair_transition=True).write({
            'repair_route': False,
            'repair_substate': 'diagnosis',
            'retire_approved_by_id': False,
            'retire_approved_date': False,
            'retire_proposed': False,
        })
        return True

    def action_reset_repair_route(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only a Helpdesk Manager can reset a repair route.'))
        if not self.asset_id or self.repair_substate == 'diagnosis':
            raise UserError(_('There is no started repair route to reset.'))
        previous_state = self.asset_state_before_repair
        if previous_state in ('available', 'assigned'):
            self.asset_id.with_context(buz_repair_transition=True).write({'state': previous_state})
        self.with_context(buz_repair_transition=True).write({
            'repair_route': False,
            'repair_substate': 'diagnosis',
            'asset_state_before_repair': False,
            'retire_proposed': False,
            'retire_approved_by_id': False,
            'retire_approved_date': False,
        })
        self.message_post(body=_('Repair route reset by the Helpdesk Manager.'))
        return True

    def action_user_report_sent(self, values):
        self.ensure_one()
        if self.env.user != self.requester_id:
            raise UserError(_('Only the requester can report an external handover.'))
        if self.repair_route != 'external_requester' or self.repair_substate != 'awaiting_user_send':
            raise UserError(_('This Ticket is not awaiting a user handover.'))
        if not values.get('requester_sent_date') or not values.get('requester_vendor_name'):
            raise ValidationError(_('Enter the sent date and repair vendor.'))
        values.update({'repair_substate': 'awaiting_return'})
        self.with_context(buz_user_repair_report=True).write(values)
        if self.assigned_user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo', user_id=self.assigned_user_id.id,
                summary=_('User Reported Asset Sent'),
                note=_('The requester reported that Asset %(asset)s was sent for repair.', asset=self.asset_id.display_name),
            )
        self.message_post(body=_('Requester reported that the Asset was sent for external repair.'))
        return True

    def action_open_user_report_sent(self):
        self.ensure_one()
        if self.env.user != self.requester_id:
            raise UserError(_('Only the requester can report an external handover.'))
        if self.repair_substate != 'awaiting_user_send':
            raise UserError(_('This Ticket is not awaiting a user handover.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Report Asset Sent'),
            'res_model': 'buz.helpdesk.ticket.repair.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_report_kind': 'sent',
            },
        }

    def action_user_report_returned(self, values):
        self.ensure_one()
        if self.env.user != self.requester_id:
            raise UserError(_('Only the requester can report an external return.'))
        if self.repair_route != 'external_requester' or self.repair_substate != 'awaiting_return':
            raise UserError(_('This Ticket is not awaiting a user repair return.'))
        if not values.get('requester_return_date') or not values.get('requester_repair_result'):
            raise ValidationError(_('Enter the return date and repair result.'))
        values.update({'repair_substate': 'awaiting_verification'})
        self.with_context(buz_user_repair_report=True).write(values)
        if self.assigned_user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo', user_id=self.assigned_user_id.id,
                summary=_('User Reported Asset Returned'),
                note=_('The requester reported that Asset %(asset)s was returned from repair.', asset=self.asset_id.display_name),
            )
        self.message_post(body=_('Requester reported that the Asset was returned from external repair.'))
        return True

    def action_open_user_report_returned(self):
        self.ensure_one()
        if self.env.user != self.requester_id:
            raise UserError(_('Only the requester can report an external return.'))
        if self.repair_substate != 'awaiting_return':
            raise UserError(_('This Ticket is not awaiting a user repair return.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Report Asset Returned'),
            'res_model': 'buz.helpdesk.ticket.repair.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_report_kind': 'returned',
            },
        }

    def action_close_ticket(self):
        self.ensure_one()
        if self.asset_id:
            self._check_repair_permission()
            if self.repair_substate != 'ready_close':
                raise UserError(_('Complete the repair process before closing this Ticket.'))
            if not self.repair_result and self.requester_repair_result:
                self.with_context(buz_repair_transition=True).write({
                    'repair_result': self.requester_repair_result,
                })
            if not self.repair_result:
                raise UserError(_('Enter the repair result before closing this Ticket.'))
            if self.repair_route == 'retire' and not self.retire_approved_by_id:
                raise UserError(_('Manager approval is required before retiring the Asset.'))
        result = super().action_close_ticket()
        if self.asset_id:
            self.env['buz.it.asset.maintenance']._create_from_ticket(self)
            target_state = 'retired' if self.repair_route == 'retire' else self.asset_state_before_repair
            if target_state not in ('available', 'assigned', 'retired'):
                target_state = 'available'
            self.asset_id.with_context(buz_repair_transition=True).write({'state': target_state})
        return result


class HelpdeskTicketRepairReportWizard(models.TransientModel):
    _name = 'buz.helpdesk.ticket.repair.report.wizard'
    _description = 'User External Repair Report'

    ticket_id = fields.Many2one('buz.helpdesk.ticket', required=True, readonly=True)
    report_kind = fields.Selection([
        ('sent', 'Report Sent'), ('returned', 'Report Returned'),
    ], required=True, readonly=True)
    sent_date = fields.Date()
    vendor_name = fields.Char()
    expected_return_date = fields.Date()
    return_date = fields.Date()
    repair_result = fields.Text()
    cost = fields.Monetary(currency_field='currency_id')
    warranty = fields.Char()
    attachment_ids = fields.Many2many('ir.attachment', string='Evidence')
    currency_id = fields.Many2one(related='ticket_id.currency_id', readonly=True)

    def action_submit(self):
        self.ensure_one()
        if self.report_kind == 'sent':
            self.ticket_id.action_user_report_sent({
                'requester_sent_date': self.sent_date,
                'requester_vendor_name': self.vendor_name,
                'requester_expected_return_date': self.expected_return_date,
                'attachment_ids': [fields.Command.link(attachment.id) for attachment in self.attachment_ids],
            })
        else:
            self.ticket_id.action_user_report_returned({
                'requester_return_date': self.return_date,
                'requester_repair_result': self.repair_result,
                'requester_cost': self.cost,
                'requester_warranty': self.warranty,
                'attachment_ids': [fields.Command.link(attachment.id) for attachment in self.attachment_ids],
            })
        return {'type': 'ir.actions.act_window_close'}


class ITAssetMaintenance(models.Model):
    _inherit = 'buz.it.asset.maintenance'

    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket', string='Source Ticket', ondelete='restrict',
        index=True, copy=False,
    )
    asset_type_id = fields.Many2one(related='asset_id.type_id', readonly=True)
    repair_route = fields.Selection(related='ticket_id.repair_route', readonly=True)
    diagnosis = fields.Text(related='ticket_id.diagnosis', readonly=True)
    repair_result = fields.Text(related='ticket_id.repair_result', readonly=True)
    parts_details = fields.Text(related='ticket_id.parts_details', readonly=True)
    parts_reference = fields.Char(related='ticket_id.parts_reference', readonly=True)
    parts_order_date = fields.Date(related='ticket_id.parts_order_date', readonly=True)
    parts_received_date = fields.Date(related='ticket_id.parts_received_date', readonly=True)
    external_sent_date = fields.Date(related='ticket_id.external_sent_date', readonly=True)
    external_expected_return_date = fields.Date(related='ticket_id.external_expected_return_date', readonly=True)
    external_return_date = fields.Date(related='ticket_id.external_return_date', readonly=True)
    external_reference = fields.Char(related='ticket_id.external_reference', readonly=True)
    external_quote = fields.Monetary(related='ticket_id.external_quote', readonly=True)
    external_cost = fields.Monetary(related='ticket_id.external_cost', readonly=True)
    external_warranty = fields.Char(related='ticket_id.external_warranty', readonly=True)
    requester_sent_date = fields.Date(related='ticket_id.requester_sent_date', readonly=True)
    requester_vendor_name = fields.Char(related='ticket_id.requester_vendor_name', readonly=True)
    requester_return_date = fields.Date(related='ticket_id.requester_return_date', readonly=True)
    requester_cost = fields.Monetary(related='ticket_id.requester_cost', readonly=True)
    requester_warranty = fields.Char(related='ticket_id.requester_warranty', readonly=True)
    retirement_reason = fields.Selection(related='ticket_id.retire_reason', readonly=True)
    retirement_details = fields.Text(related='ticket_id.retire_reason_detail', readonly=True)

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
        if self.search_count([('ticket_id', '=', ticket.id)]):
            raise UserError(_('This Ticket already has a maintenance history.'))
        employee = ticket.assigned_user_id.employee_id
        vals = {
            'ticket_id': ticket.id,
            'asset_id': ticket.asset_id.id,
            'sent_date': ticket.create_ticket_date or fields.Date.context_today(ticket),
            'symptom': ticket.description or ticket.subject,
            'state': 'done',
            'completed_date': ticket.closed_ticket_date or fields.Date.context_today(ticket),
            'technician_employee_id': employee.id if employee and employee.company_id == ticket.company_id else False,
            'external_technician_name': ticket.external_technician_name or ticket.requester_vendor_name,
            'vendor_id': ticket.external_vendor_id,
            'cost': ticket.external_cost or ticket.requester_cost,
            'notes': ticket.repair_result or ticket.requester_repair_result,
            'attachment_ids': [fields.Command.set(ticket.attachment_ids.ids)],
        }
        return self.with_context(buz_repair_history_from_ticket=True).sudo().create(vals)
