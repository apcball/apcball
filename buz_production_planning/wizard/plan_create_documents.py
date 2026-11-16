# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from datetime import datetime, time

import pytz
from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PlanCreateDocuments(models.TransientModel):
    _name = 'buz.plan.create.documents.wizard'
    _description = 'Create MO / PO Drafts from Plan Suggestions'

    run_id = fields.Many2one('buz.plan.run', required=True, readonly=True)
    suggestion_ids = fields.Many2many(
        'buz.plan.suggestion', string="Suggestions",
        domain="[('run_id', '=', run_id), ('state', 'in', ('proposed', 'approved'))]")
    summary = fields.Html(compute='_compute_summary', sanitize=False)

    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('active_model') == 'buz.plan.suggestion' and ctx.get('active_ids'):
            sugg = self.env['buz.plan.suggestion'].browse(ctx['active_ids'])
            runs = sugg.run_id
            if len(runs) != 1:
                raise UserError(_("Select suggestions from one plan at a time."))
            res.update(run_id=runs.id, suggestion_ids=[Command.set(
                sugg.filtered(lambda s: s.state in ('proposed', 'approved')).ids)])
        elif res.get('run_id') or ctx.get('default_run_id'):
            run = self.env['buz.plan.run'].browse(res.get('run_id') or ctx['default_run_id'])
            res.update(run_id=run.id, suggestion_ids=[Command.set(
                run.suggestion_ids.filtered(
                    lambda s: s.state == 'approved' and not s.production_id
                    and not s.purchase_line_id).ids)])
        return res

    # ------------------------------------------------------------------
    def _classify(self):
        """Split the selection into what will be created and what is skipped."""
        make, buy, no_vendor, no_line, existing = (self.env['buz.plan.suggestion'] for _i in range(5))
        for s in self.suggestion_ids:
            if s.state == 'rejected':
                continue
            if s.production_id or s.purchase_line_id or s.state == 'done':
                existing |= s
            elif s.action == 'make':
                if s.picking_type_id:
                    make |= s
                else:
                    no_line |= s
            elif s.vendor_id:
                buy |= s
            else:
                no_vendor |= s
        return make, buy, no_vendor, no_line, existing

    @api.depends('suggestion_ids', 'suggestion_ids.state', 'suggestion_ids.vendor_id',
                 'suggestion_ids.picking_type_id')
    def _compute_summary(self):
        for wiz in self:
            make, buy, no_vendor, no_line, existing = wiz._classify()  # pylint: disable=protected-access
            rows = [
                _("Manufacturing orders (draft): %s", len(make)),
                _("Purchase orders (draft): %(po)s for %(lines)s lines",
                  po=len(buy.vendor_id), lines=len(buy)),
            ]
            if buy:
                rows.append(_("Vendors: %s", ", ".join(buy.vendor_id.mapped('display_name'))))
            if no_vendor:
                rows.append(_("Skipped, no vendor: %s", ", ".join(
                    no_vendor.product_id.mapped('display_name'))))
            if no_line:
                rows.append(_("Blocked, no production line: %s", ", ".join(
                    no_line.product_id.mapped('display_name'))))
            if existing:
                rows.append(_("Skipped, document already created: %s", len(existing)))
            wiz.summary = Markup("<ul>%s</ul>") % Markup("").join(
                Markup("<li>%s</li>") % escape(r) for r in rows)

    def _local_to_utc(self, day, hour):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')
        local = tz.localize(datetime.combine(day, time(hour)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    def _create_documents(self):
        """Create draft MOs and POs. Returns a dict of what happened.

        Nothing is confirmed, reserved or moved: only mrp.production in
        draft and purchase.order in draft (RFQ) are created.
        """
        self.ensure_one()
        run = self.run_id
        if run.state in ('cancel', 'draft'):
            raise UserError(_(
                "Plan %s must be computed before documents can be created.", run.name))
        if any(s.run_id != run for s in self.suggestion_ids):
            raise UserError(_("All suggestions must belong to plan %s.", run.name))
        if not self.suggestion_ids:
            raise UserError(_("Select at least one suggestion."))

        proposed = self.suggestion_ids.filtered(lambda s: s.state == 'proposed')
        proposed.action_approve()
        make, buy, no_vendor, no_line, existing = self._classify()  # rejected are left out
        if no_line:
            raise UserError(_(
                "These products have no production line. Set 'Production Line' in "
                "Production Planning > Configuration > Product Parameters, then compute the plan "
                "again:\n%s", "\n".join(no_line.product_id.mapped('display_name'))))

        Production = self.env['mrp.production']
        mos = Production
        blocked = []
        analytics = self._latest_mo_analytics(make.product_id.ids, run.company_id.id)
        for s in make:
            vals = {
                'product_id': s.product_id.id,
                'product_qty': s.qty,
                'product_uom_id': s.uom_id.id,
                'bom_id': s.bom_id.id,
                'picking_type_id': s.picking_type_id.id,
                'company_id': run.company_id.id,
                'origin': run.name,
                'date_start': self._local_to_utc(s.date_release, 8),
                'date_deadline': self._local_to_utc(s.date_need, 17),
            }
            if analytics.get(s.product_id.id):
                vals['analytic_distribution'] = analytics[s.product_id.id]
            try:
                # One MO refused by a validation (prod: mandatory analytic plans)
                # must not cancel the whole batch; it is reported instead.
                with self.env.cr.savepoint():
                    mo = Production.create(vals)
                    mo.flush_recordset()
            except (UserError, ValidationError) as exc:
                blocked.append((s, str(exc.args[0] if exc.args else exc)))
                continue
            s.write({'production_id': mo.id, 'state': 'done'})
            mos |= mo

        orders = self.env['purchase.order']
        by_vendor = {}
        for s in buy:
            by_vendor.setdefault(s.vendor_id, self.env['buz.plan.suggestion'])
            by_vendor[s.vendor_id] |= s
        for vendor, suggestions in by_vendor.items():
            order = self.env['purchase.order'].create({
                'partner_id': vendor.id,
                'company_id': run.company_id.id,
                'origin': run.name,
                'date_planned': self._local_to_utc(min(suggestions.mapped('date_need')), 8),
                'order_line': [Command.create(self._po_line_vals(s)) for s in suggestions],
            })
            for s, line in zip(suggestions, order.order_line):
                s.write({'purchase_line_id': line.id, 'state': 'done'})
            orders |= order

        open_left = run.suggestion_ids.filtered(lambda s: s.state in ('proposed', 'approved'))
        run.state = 'confirmed' if open_left else 'done'
        result = {
            'productions': mos, 'orders': orders, 'no_vendor': no_vendor, 'existing': existing,
            'blocked': blocked,
        }
        run.message_post(body=self._result_body(result))
        return result

    def _latest_mo_analytics(self, product_ids, company_id):
        """Analytic distribution of each product's latest MO. Prod requires
        BU + Production plans on every MO and has no distribution model, so a
        draft MO copies what the planners used last time (editable on the MO)."""
        if not product_ids or 'analytic_distribution' not in self.env['mrp.production']._fields:
            return {}
        self.env['mrp.production'].flush_model(
            ['product_id', 'company_id', 'state', 'analytic_distribution'])
        self.env.cr.execute("""
            SELECT DISTINCT ON (product_id) product_id, analytic_distribution
              FROM mrp_production
             WHERE product_id IN %s AND company_id = %s AND state != 'cancel'
               AND analytic_distribution IS NOT NULL
             ORDER BY product_id, id DESC
        """, (tuple(product_ids), company_id))
        return dict(self.env.cr.fetchall())

    def _po_line_vals(self, s):
        product = s.product_id
        uom = product.uom_po_id or product.uom_id
        return {
            'product_id': product.id,
            'product_qty': s.uom_id._compute_quantity(s.qty, uom),  # pylint: disable=protected-access
            'product_uom': uom.id,
            'date_planned': self._local_to_utc(s.date_need, 8),
        }

    def _result_body(self, result):
        rows = [
            _("Created %(mo)s draft manufacturing orders and %(po)s draft purchase orders.",
              mo=len(result['productions']), po=len(result['orders'])),
        ]
        if result['productions']:
            rows.append(", ".join(result['productions'].mapped('name')))
        if result['orders']:
            rows.append(", ".join(result['orders'].mapped('name')))
        if result['no_vendor']:
            rows.append(_("Skipped, no vendor: %s", ", ".join(
                result['no_vendor'].product_id.mapped('display_name'))))
        if result['existing']:
            rows.append(_("Skipped, document already created: %s", len(result['existing'])))
        for s, message in result.get('blocked', []):
            rows.append(_("Not created, %(product)s: %(reason)s",
                          product=s.product_id.display_name, reason=message))
        return Markup("<br/>").join(escape(r) for r in rows)

    def action_create(self):
        result = self._create_documents()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Documents created"),
                'message': _("%(mo)s manufacturing orders, %(po)s purchase orders (all draft). "
                             "Skipped: %(skip)s.",
                             mo=len(result['productions']), po=len(result['orders']),
                             skip=len(result['no_vendor']) + len(result['existing'])
                             + len(result['blocked'])),
                'type': 'warning' if result['blocked'] else 'success',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
