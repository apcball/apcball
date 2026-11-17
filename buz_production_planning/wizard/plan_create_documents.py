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
    buy_document = fields.Selection([
        ('bo', "Blanket Order"),
        ('rfq', "Purchase Order (RFQ)"),
    ], string="Buy Suggestions Become", default='bo', required=True,
        help="Blanket Order: an agreement with the vendor, purchasing issues the purchase orders "
             "from it later. RFQ: one draft purchase order per vendor, now.")
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
                    and not s.purchase_line_id and not s.requisition_line_id).ids)])
        return res

    # ------------------------------------------------------------------
    def _classify(self):
        """Split the selection into what will be created and what is skipped."""
        make, buy, no_vendor, no_line, existing = (self.env['buz.plan.suggestion'] for _i in range(5))
        for s in self.suggestion_ids:
            if s.state == 'rejected':
                continue
            if s.production_id or s.purchase_line_id or s.requisition_line_id or s.state == 'done':
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
                 'suggestion_ids.picking_type_id', 'buy_document')
    def _compute_summary(self):
        for wiz in self:
            make, buy, no_vendor, no_line, existing = wiz._classify()  # pylint: disable=protected-access
            create, attention = [], []
            create.append(_("Manufacturing orders (draft): %s", len(make)))
            vendors = ", ".join(buy.vendor_id.mapped('display_name'))
            if wiz.buy_document == 'bo':
                create.append(_("Blanket orders (draft): %(bo)s for %(lines)s lines",
                                bo=len(buy.vendor_id), lines=len(buy)))
            else:
                create.append(_("Purchase orders (RFQ, draft): %(po)s for %(lines)s lines",
                                po=len(buy.vendor_id), lines=len(buy)))
            if buy:
                create.append(_("Vendors: %s", vendors))
            if no_vendor:
                attention.append(_(
                    "No vendor, not created: %s. Set a vendor on the suggestion or on the "
                    "product, then create again.",
                    ", ".join(no_vendor.product_id.mapped('display_name'))))
            if no_line:
                attention.append(_(
                    "No production line, cannot create: %s. Set 'Production Line' in "
                    "Product Parameters.", ", ".join(no_line.product_id.mapped('display_name'))))
            prep = {'no_price': (), 'no_analytic': ()}
            if wiz.buy_document == 'bo' and buy:
                try:
                    prep = wiz._blanket_order_plan(buy)  # pylint: disable=protected-access
                except UserError as exc:
                    attention.append(str(exc.args[0] if exc.args else exc))
                if prep['no_price']:
                    attention.append(_(
                        "No price found, the line is created with price 0: %s. Enter the price "
                        "before purchasing confirms the blanket order.",
                        ", ".join(prep['no_price'].product_id.mapped('display_name'))))
                if prep['no_analytic']:
                    attention.append(_(
                        "No analytic distribution found: %s. Fill it in on the blanket order "
                        "line, otherwise the purchase orders issued from it will be refused.",
                        ", ".join(prep['no_analytic'].product_id.mapped('display_name'))))
            if existing:
                attention.append(_(
                    "Already has a document, skipped: %s. Nothing to do.", len(existing)))
            blocks = [(_("Will be created"), create)]
            if attention:
                blocks.append((_("Needs attention"), attention))
            wiz.summary = Markup("").join(
                Markup("<p class='mb-1 fw-bold'>%s</p><ul>%s</ul>") % (
                    title, Markup("").join(Markup("<li>%s</li>") % escape(r) for r in rows))
                for title, rows in blocks)

    def _local_to_utc(self, day, hour, minute=0):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')
        local = tz.localize(datetime.combine(day, time(hour, minute)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    def _create_documents(self):
        """Create draft MOs and draft blanket orders / RFQs. Returns a dict of what happened.

        Nothing is confirmed, reserved or moved: only mrp.production, purchase.requisition
        and purchase.order in draft are created.
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

        if self.buy_document == 'bo':
            requisitions, orders, bo_notes = self._create_blanket_orders(buy, blocked)
        else:
            requisitions = self.env['purchase.requisition']
            orders, bo_notes = self._create_rfqs(buy), {}

        open_left = run.suggestion_ids.filtered(lambda s: s.state in ('proposed', 'approved'))
        run.state = 'confirmed' if open_left else 'done'
        result = {
            'productions': mos, 'orders': orders, 'requisitions': requisitions,
            'no_vendor': no_vendor, 'existing': existing, 'blocked': blocked,
            'no_price': bo_notes.get('no_price', self.env['buz.plan.suggestion']),
            'no_analytic': bo_notes.get('no_analytic', self.env['buz.plan.suggestion']),
        }
        run.message_post(body=self._result_body(result))
        return result

    def _group_by_vendor(self, buy):
        by_vendor = {}
        for s in buy:
            by_vendor.setdefault(s.vendor_id, self.env['buz.plan.suggestion'])
            by_vendor[s.vendor_id] |= s
        return by_vendor

    def _create_rfqs(self, buy):
        """One draft RFQ per vendor, always a new one."""
        orders = self.env['purchase.order']
        run = self.run_id
        for vendor, suggestions in self._group_by_vendor(buy).items():
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
        return orders

    def _create_blanket_orders(self, buy, blocked):
        """One draft blanket order per vendor, always a new one, never confirmed.

        A vendor whose order is refused by a validation goes to ``blocked``;
        the other vendors still get their document.
        """
        run = self.run_id
        Requisition = self.env['purchase.requisition']
        requisitions = Requisition
        prep = self._blanket_order_plan(buy)
        for vendor, suggestions in self._group_by_vendor(buy).items():
            header = {**prep['headers'][vendor.id], 'buz_plan_run_id': run.id}
            try:
                with self.env.cr.savepoint():
                    requisition = Requisition.create(header)
                    # Explicit lines in suggestion order: line i belongs to suggestion i.
                    lines = self.env['purchase.requisition.line'].create([
                        {**prep['lines'][s.id], 'requisition_id': requisition.id}
                        for s in suggestions])
                    requisition.flush_recordset()
                    lines.flush_recordset()
            except (UserError, ValidationError) as exc:
                blocked.extend((s, str(exc.args[0] if exc.args else exc)) for s in suggestions)
                continue
            for s, line in zip(suggestions, lines):
                s.write({'requisition_line_id': line.id, 'state': 'done'})
            requisitions |= requisition
        done = requisitions.line_ids
        created = buy.filtered(lambda s: s.requisition_line_id in done)
        return requisitions, self.env['purchase.order'], {
            'no_price': prep['no_price'] & created, 'no_analytic': prep['no_analytic'] & created}

    # -- blanket order values -------------------------------------------
    def _blanket_order_type(self):
        rtype = self.env['purchase.requisition.type'].search(
            [('quantity_copy', '=', 'none')], limit=1)
        if not rtype:
            raise UserError(_(
                "No blanket order type is configured. In Purchase > Configuration > Agreement "
                "Types, create a type with Quantities = 'Set quantities manually'."))
        return rtype

    def _blanket_order_plan(self, buy):
        """Header and line values of the blanket orders for ``buy``, plus the
        suggestions whose price or analytic could not be found. Read-only."""
        self.ensure_one()
        run = self.run_id
        Suggestion = self.env['buz.plan.suggestion']
        company = run.company_id
        today = fields.Date.context_today(self)
        res = {'headers': {}, 'lines': {}, 'no_price': Suggestion, 'no_analytic': Suggestion}
        if not buy:
            return res
        self.env.flush_all()
        rtype = self._blanket_order_type()
        vendors = buy.vendor_id
        latest = self._latest_bo_header(vendors.ids, company.id)
        warehouses = run.warehouse_ids
        receipt_type = warehouses[:1].in_type_id
        for vendor in vendors:
            sugg = buy.filtered(lambda s, v=vendor: s.vendor_id == v)
            prev = latest.get(vendor.id, {})
            currency = (self.env['res.currency'].browse(prev['currency_id']) if prev.get('currency_id')
                        else vendor.with_company(company).property_purchase_currency_id
                        or company.currency_id)
            header = {
                'vendor_id': vendor.id, 'company_id': company.id, 'type_id': rtype.id,
                'currency_id': currency.id, 'origin': run.name, 'user_id': self.env.user.id,
                'ordering_date': today,
                'schedule_date': min(sugg.mapped('date_need')),
                'date_end': self._local_to_utc(run.date_to, 23, 59),
            }
            # The receipt type must belong to a warehouse the plan counts as supply, or the
            # received quantity would never be netted and the purchase proposed again.
            picking_type = self.env['stock.picking.type'].browse(prev.get('picking_type_id', 0)).exists()
            if not (picking_type and picking_type.warehouse_id in warehouses):
                picking_type = receipt_type
            if picking_type:
                header['picking_type_id'] = picking_type.id
            res['headers'][vendor.id] = header
        analytics = self._latest_line_analytics(buy.product_id.ids, company.id)
        prices = self._latest_line_prices(buy, company.id)
        for s in buy:
            header = res['headers'][s.vendor_id.id]
            currency = self.env['res.currency'].browse(header['currency_id'])
            product = s.product_id
            uom = product.uom_po_id or product.uom_id
            qty = s.uom_id._compute_quantity(s.qty, uom)  # pylint: disable=protected-access
            price = self._blanket_price(s, uom, qty, currency, today, prices)
            analytic = analytics.get(product.id)
            if not price:
                res['no_price'] |= s
            if not analytic:
                res['no_analytic'] |= s
            vals = {
                'product_id': product.id, 'product_uom_id': uom.id, 'product_qty': qty,
                'schedule_date': s.date_need, 'price_unit': price or 0.0}
            if analytic:
                vals['analytic_distribution'] = analytic
            res['lines'][s.id] = vals
        return res

    def _latest_bo_header(self, vendor_ids, company_id):
        """Currency and receipt type of each vendor's latest non-cancelled blanket order."""
        self.env.cr.execute("""
            SELECT DISTINCT ON (r.vendor_id) r.vendor_id, r.currency_id, r.picking_type_id
              FROM purchase_requisition r
              JOIN purchase_requisition_type t ON t.id = r.type_id
             WHERE r.vendor_id IN %s AND r.company_id = %s AND r.state != 'cancel'
               AND t.quantity_copy = 'none'
             ORDER BY r.vendor_id, r.id DESC
        """, (tuple(vendor_ids), company_id))
        return {vid: {'currency_id': cur, 'picking_type_id': pt}
                for vid, cur, pt in self.env.cr.fetchall()}

    def _latest_line_analytics(self, product_ids, company_id):
        """Analytic distribution of each product's latest blanket order line that has one,
        else of its latest purchase order line that has one (prod: analytic is mandatory
        on purchase orders and a PO issued from a blanket order copies the line's)."""
        out = {}
        if not product_ids:
            return out
        cr = self.env.cr
        cr.execute("""
            SELECT DISTINCT ON (l.product_id) l.product_id, l.analytic_distribution
              FROM purchase_requisition_line l
              JOIN purchase_requisition r ON r.id = l.requisition_id
             WHERE l.product_id IN %s AND r.company_id = %s AND r.state != 'cancel'
               AND l.analytic_distribution IS NOT NULL AND l.analytic_distribution::text != '{}'
             ORDER BY l.product_id, r.id DESC, l.id DESC
        """, (tuple(product_ids), company_id))
        out.update(cr.fetchall())
        missing = tuple(set(product_ids) - set(out))
        if missing:
            cr.execute("""
                SELECT DISTINCT ON (l.product_id) l.product_id, l.analytic_distribution
                  FROM purchase_order_line l
                  JOIN purchase_order o ON o.id = l.order_id
                 WHERE l.product_id IN %s AND o.company_id = %s AND o.state != 'cancel'
                   AND l.analytic_distribution IS NOT NULL AND l.analytic_distribution::text != '{}'
                 ORDER BY l.product_id, o.id DESC, l.id DESC
            """, (missing, company_id))
            out.update(cr.fetchall())
        return out

    def _latest_line_prices(self, buy, company_id):
        """Latest priced blanket order line and latest confirmed PO line of each
        (vendor, product), with the unit and currency the price is expressed in."""
        pairs = {(s.vendor_id.id, s.product_id.id) for s in buy}
        cr = self.env.cr
        vendors, products = tuple({v for v, _p in pairs}), tuple({p for _v, p in pairs})
        out = {'bo': {}, 'po': {}}
        cr.execute("""
            SELECT DISTINCT ON (r.vendor_id, l.product_id)
                   r.vendor_id, l.product_id, l.price_unit, l.product_uom_id, r.currency_id
              FROM purchase_requisition_line l
              JOIN purchase_requisition r ON r.id = l.requisition_id
             WHERE r.vendor_id IN %s AND l.product_id IN %s AND r.company_id = %s
               AND r.state != 'cancel' AND l.price_unit > 0
             ORDER BY r.vendor_id, l.product_id, r.id DESC, l.id DESC
        """, (vendors, products, company_id))
        for vid, pid, price, uom, cur in cr.fetchall():
            out['bo'][(vid, pid)] = (price, uom, cur)
        cr.execute("""
            SELECT DISTINCT ON (o.partner_id, l.product_id)
                   o.partner_id, l.product_id, l.price_unit, l.product_uom, o.currency_id
              FROM purchase_order_line l
              JOIN purchase_order o ON o.id = l.order_id
             WHERE o.partner_id IN %s AND l.product_id IN %s AND o.company_id = %s
               AND o.state IN ('purchase', 'done') AND l.price_unit > 0
             ORDER BY o.partner_id, l.product_id, o.date_order DESC, l.id DESC
        """, (vendors, products, company_id))
        for vid, pid, price, uom, cur in cr.fetchall():
            out['po'][(vid, pid)] = (price, uom, cur)
        return out

    def _blanket_price(self, s, uom, qty, currency, today, prices):
        """Unit price per ``uom`` in ``currency``: vendor pricelist, then the latest
        blanket order line, then the latest confirmed PO line. 0.0 when none exists."""
        company = self.run_id.company_id
        product = s.product_id.with_company(company)
        seller = product._select_seller(  # pylint: disable=protected-access
            partner_id=s.vendor_id, quantity=qty, date=today, uom_id=uom)
        candidates = []
        if seller and seller.price:
            candidates.append((seller.price, seller.product_uom, seller.currency_id))
        for source in ('bo', 'po'):
            hit = prices[source].get((s.vendor_id.id, s.product_id.id))
            if hit:
                candidates.append((
                    hit[0], self.env['uom.uom'].browse(hit[1]), self.env['res.currency'].browse(hit[2])))
        for price, from_uom, from_currency in candidates:
            if from_uom:
                price = from_uom._compute_price(price, uom)  # pylint: disable=protected-access
            if from_currency and from_currency != currency:
                price = from_currency._convert(price, currency, company, today)
            return price
        return 0.0

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
        rows = [escape(_(
            "Created %(mo)s draft manufacturing orders, %(bo)s draft blanket orders and "
            "%(po)s draft purchase orders.",
            mo=len(result['productions']), bo=len(result['requisitions']),
            po=len(result['orders'])))]
        links = [mo._get_html_link() for mo in result['productions']]
        for bo in result['requisitions']:
            # A draft blanket order is still named "New": show the vendor instead.
            links.append(bo._get_html_link(
                title=_("Blanket Order (draft) - %s", bo.vendor_id.display_name)
                if bo.name == 'New' else None))
        links += [po._get_html_link() for po in result['orders']]
        if links:
            rows.append(Markup(", ").join(links))
        if result['no_vendor']:
            rows.append(escape(_("Skipped, no vendor: %s", ", ".join(
                result['no_vendor'].product_id.mapped('display_name')))))
        if result['no_price']:
            rows.append(escape(_("No price found (price 0): %s", ", ".join(
                result['no_price'].product_id.mapped('display_name')))))
        if result['no_analytic']:
            rows.append(escape(_("No analytic distribution found: %s", ", ".join(
                result['no_analytic'].product_id.mapped('display_name')))))
        if result['existing']:
            rows.append(escape(_("Skipped, document already created: %s", len(result['existing']))))
        for s, message in result.get('blocked', []):
            rows.append(escape(_("Not created, %(product)s: %(reason)s",
                                 product=s.product_id.display_name, reason=message)))
        return Markup("<br/>").join(rows)

    def action_create(self):
        run = self.run_id
        result = self._create_documents()
        n_skipped = len(result['no_vendor']) + len(result['existing']) + len(result['blocked'])
        message = _(
            "%(mo)s manufacturing orders, %(bo)s blanket orders, %(po)s purchase orders "
            "(all draft, nothing confirmed).",
            mo=len(result['productions']), bo=len(result['requisitions']),
            po=len(result['orders']))
        if n_skipped:
            message += " " + _("Not created: %(skip)s. See the plan's chatter for the reasons.",
                               skip=n_skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Documents created"),
                'message': message,
                'type': 'warning' if (result['blocked'] or n_skipped) else 'success',
                'sticky': bool(n_skipped),
                # Closing the dialog makes the plan form reload its record (stat buttons and
                # next-step banner refresh). From the Suggestions list there is no plan form
                # underneath, so open it.
                'next': {'type': 'ir.actions.act_window_close'}
                if self.env.context.get('active_model') == 'buz.plan.run' else {
                    'type': 'ir.actions.act_window', 'res_model': 'buz.plan.run',
                    'res_id': run.id, 'views': [(False, 'form')], 'target': 'main'},
            },
        }
