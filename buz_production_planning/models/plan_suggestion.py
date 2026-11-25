# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PlanSuggestion(models.Model):
    _name = 'buz.plan.suggestion'
    _description = 'Plan Suggestion (Make / Buy)'
    _inherit = ['mail.thread']
    _check_company_auto = True
    _order = 'run_id, level, date_release, product_id'

    run_id = fields.Many2one('buz.plan.run', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='run_id.company_id', store=True, index=True, readonly=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True, check_company=True)
    action = fields.Selection([('make', "Make"), ('buy', "Buy")], required=True)
    qty = fields.Float(digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string="Unit", required=True)
    date_need = fields.Date(
        string="Needed By", required=True,
        help="The date the stock must be available.")
    date_release = fields.Date(
        string="Order / Start By", required=True,
        help="The date to start the manufacturing order or place the purchase so it arrives in time.")
    is_late = fields.Boolean(
        string="Late", readonly=True,
        help="The release date was already in the past when the plan was computed.")
    bom_id = fields.Many2one('mrp.bom', check_company=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type', string="Production Line", check_company=True,
        domain=[('code', '=', 'mrp_operation')])
    vendor_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)])
    level = fields.Integer(string="BoM Level", readonly=True)
    onhand_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    incoming_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    demand_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    projected_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    shortage_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    parent_suggestion_id = fields.Many2one(
        'buz.plan.suggestion', string="Pegged To", ondelete='set null', index=True)
    state = fields.Selection([
        ('proposed', "Proposed"),
        ('approved', "Approved"),
        ('rejected', "Rejected"),
        ('done', "Done"),
    ], default='proposed', required=True, index=True, tracking=True)
    production_id = fields.Many2one(
        'mrp.production', string="Manufacturing Order", readonly=True, copy=False,
        check_company=True, index=True,
        help="The draft manufacturing order created from this Make suggestion.")
    purchase_line_id = fields.Many2one(
        'purchase.order.line', string="RFQ Line", readonly=True, copy=False,
        check_company=True, index=True,
        help="The line of the RFQ created from this Buy suggestion (RFQ choice in Create Documents).")
    purchase_order_id = fields.Many2one(
        'purchase.order', string="Purchase Order", related='purchase_line_id.order_id',
        readonly=True, help="The RFQ created directly from this Buy suggestion.")
    requisition_line_id = fields.Many2one(
        'purchase.requisition.line', string="Blanket Order Line", readonly=True, copy=False,
        check_company=True, index=True,
        help="The line of the draft blanket order created from this Buy suggestion.")
    requisition_id = fields.Many2one(
        'purchase.requisition', string="Blanket Order", related='requisition_line_id.requisition_id',
        store=True, index=True, readonly=True,
        help="The blanket order created from this Buy suggestion. Purchasing issues the "
             "purchase orders from it.")
    document_ref = fields.Char(
        string="Document", compute='_compute_document_ref',
        help="The manufacturing order, blanket order or purchase order created from this suggestion.")
    document_state = fields.Selection([
        ('none', "No Document"),
        ('draft', "Draft"),
        ('open', "In Progress"),
        ('done', "Done"),
        ('cancel', "Cancelled"),
    ], string="Document Status", compute='_compute_document_state', store=True, index=True,
        help="Where the created document stands: still a draft, in progress, done or cancelled.")
    explanation = fields.Text(
        string="Explanation", compute='_compute_explanation',
        help="Why this suggestion exists, in plain words.")

    _sql_constraints = [
        ('qty_positive', 'check(qty > 0)', "Suggested quantity must be greater than zero."),
    ]

    def _check_actionable(self, states):
        bad = self.filtered(lambda s: s.state not in states)
        if bad:
            raise UserError(_(
                "These suggestions are not in a state that allows this action: %s",
                ", ".join(bad.mapped('product_id.display_name'))))

    def action_approve(self):
        self._check_actionable(('proposed', 'rejected'))
        self.write({'state': 'approved'})

    def action_reject(self):
        self._check_actionable(('proposed', 'approved'))
        self.write({'state': 'rejected'})

    def action_reset(self):
        self._check_actionable(('approved', 'rejected'))
        self.write({'state': 'proposed'})

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    _MO_STATE = {'draft': 'draft', 'confirmed': 'open', 'progress': 'open',
                 'to_close': 'open', 'done': 'done', 'cancel': 'cancel'}
    _BO_STATE = {'draft': 'draft', 'ongoing': 'open', 'in_progress': 'open',
                 'open': 'open', 'done': 'done', 'cancel': 'cancel'}
    _PO_STATE = {'draft': 'draft', 'sent': 'draft', 'to approve': 'draft',
                 'purchase': 'open', 'done': 'done', 'cancel': 'cancel'}

    def _document(self):
        """The one document this suggestion points to (or an empty record)."""
        self.ensure_one()
        return self.production_id or self.requisition_id or self.purchase_order_id

    @api.depends('production_id.state', 'requisition_id.state', 'purchase_line_id.order_id.state')
    def _compute_document_state(self):
        for s in self:
            if s.production_id:
                s.document_state = s._MO_STATE.get(s.production_id.state, 'open')
            elif s.requisition_id:
                s.document_state = s._BO_STATE.get(s.requisition_id.state, 'open')
            elif s.purchase_order_id:
                s.document_state = s._PO_STATE.get(s.purchase_order_id.state, 'open')
            else:
                s.document_state = 'none'

    @api.depends('production_id.name', 'requisition_id.name', 'purchase_order_id.name')
    def _compute_document_ref(self):
        for s in self:
            if s.production_id:
                s.document_ref = s.production_id.name
            elif s.requisition_id:
                # A draft blanket order has no number yet: it is named "New".
                s.document_ref = (
                    _("Blanket Order (draft)") if s.requisition_id.name in (False, 'New')
                    else s.requisition_id.name)
            elif s.purchase_order_id:
                s.document_ref = s.purchase_order_id.name
            else:
                s.document_ref = False

    def action_open_document(self):
        self.ensure_one()
        doc = self._document()
        if not doc:
            raise UserError(_("No document has been created from this suggestion yet."))
        return {
            'type': 'ir.actions.act_window', 'name': doc.display_name,
            'res_model': doc._name, 'res_id': doc.id, 'view_mode': 'form',
        }

    @staticmethod
    def _fmt(qty):
        return ('%.3f' % (qty or 0.0)).rstrip('0').rstrip('.') or '0'

    @api.depends('onhand_qty', 'incoming_qty', 'demand_qty', 'projected_qty', 'shortage_qty',
                 'qty', 'action', 'uom_id')
    def _compute_explanation(self):
        for s in self:
            fmt = s._fmt
            verb = _("make") if s.action == 'make' else _("buy")
            # ``projected`` also holds the earlier suggestions of this product (the engine adds
            # each suggested quantity back before looking at the next week).
            earlier = s.projected_qty - (s.onhand_qty + s.incoming_qty - s.demand_qty)
            args = dict(
                onhand=fmt(s.onhand_qty), incoming=fmt(s.incoming_qty), demand=fmt(s.demand_qty),
                earlier=fmt(earlier), projected=fmt(s.projected_qty), short=fmt(s.shortage_qty),
                verb=verb, qty=fmt(s.qty), uom=s.uom_id.name or '')
            if abs(earlier) > 1e-6:
                text = _(
                    "On hand %(onhand)s + incoming %(incoming)s + earlier suggestions %(earlier)s "
                    "- demand %(demand)s = %(projected)s (short by %(short)s). "
                    "Suggested: %(verb)s %(qty)s %(uom)s.", **args)
            else:
                text = _(
                    "On hand %(onhand)s + incoming %(incoming)s - demand %(demand)s = %(projected)s "
                    "(short by %(short)s). Suggested: %(verb)s %(qty)s %(uom)s.", **args)
            if s.qty - s.shortage_qty > 1e-6:
                text += " " + _(
                    "More than the shortage because of the minimum batch, batch multiple or unit rounding.")
            s.explanation = text
