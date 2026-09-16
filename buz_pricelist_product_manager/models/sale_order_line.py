from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    include_installation = fields.Boolean(
        string='Include Installation',
        default=False
    )

    installation_price = fields.Float(
        string='Installation Price',
        compute='_compute_installation_price',
        store=True,
        readonly=True
    )

    install_cost = fields.Float(
        string='Installation Cost',
        compute='_compute_install_cost',
        store=True,
        readonly=True,
        help="Per-unit cost of the installation service, taken from the Standard Cost "
             "Pricelist. Added to purchase_price when the line includes installation."
    )

    @api.depends('product_id', 'order_id.pricelist_id', 'product_uom_qty', 'order_id.date_order')
    def _compute_installation_price(self):
        # Cache standard cost pricelists by company
        std_cost_pls = {}

        for line in self:
            if not line.product_id or not line.order_id.pricelist_id:
                line.installation_price = 0.0
                continue

            pricelist = line.order_id.pricelist_id
            product = line.product_id
            qty = line.product_uom_qty or 1.0
            date = line.order_id.date_order

            # If pricelist has "Use Installation Price" checked,
            # pull installation_price from the Standard Cost Pricelist
            if pricelist.use_installation_price:
                cid = line.company_id.id or line.order_id.company_id.id
                if cid not in std_cost_pls:
                    std_cost_pls[cid] = self.env['product.pricelist'].search([
                        ('is_standard_cost_pricelist', '=', True),
                        ('company_id', '=', cid),
                    ], limit=1)

                std_pl = std_cost_pls[cid]
                if std_pl:
                    rule_result = std_pl._get_product_price_rule(
                        product, quantity=1.0, date=date
                    )
                    if rule_result[1]:
                        src_item = self.env['product.pricelist.item'].browse(rule_result[1])
                        line.installation_price = src_item.installation_price or 0.0
                    else:
                        line.installation_price = 0.0
                else:
                    line.installation_price = 0.0
                continue

            # Default: pull installation_price from current pricelist rule
            rule = pricelist._get_product_price_rule(
                product, quantity=qty, date=date
            )

            rule_id = rule[1]
            if rule_id:
                item = self.env['product.pricelist.item'].browse(rule_id)
                line.installation_price = item.installation_price
            else:
                line.installation_price = 0.0

    @api.depends('product_id', 'company_id', 'order_id.pricelist_id', 'order_id.date_order')
    def _compute_install_cost(self):
        """Per-unit installation cost from the company's Standard Cost Pricelist rule.

        Always sourced from the Standard Cost Pricelist (the cost book of record),
        independent of the sale pricelist's ``use_installation_price`` flag.
        """
        std_cost_pls = {}
        Pricelist = self.env['product.pricelist']

        for line in self:
            if not line.product_id or not line.order_id:
                line.install_cost = 0.0
                continue

            company = line.company_id or line.order_id.company_id
            cid = company.id
            if cid not in std_cost_pls:
                std_cost_pls[cid] = Pricelist._get_standard_cost_pricelist(company)
            std_pl = std_cost_pls[cid]

            if not std_pl:
                line.install_cost = 0.0
                continue

            date = line.order_id.date_order or fields.Date.today()
            rule_result = std_pl._get_product_price_rule(
                line.product_id, quantity=1.0, date=date
            )
            if rule_result[1]:
                src_item = self.env['product.pricelist.item'].browse(rule_result[1])
                line.install_cost = src_item.install_cost or 0.0
            else:
                line.install_cost = 0.0

    def _expected_installation_price_unit(self):
        """price_unit the line should carry while installation is included:
        normal pricelist price + per-unit installation price."""
        self.ensure_one()
        pricelist_price = self.order_id.pricelist_id._get_product_price(
            self.product_id, self.product_uom_qty or 1.0,
            date=self.order_id.date_order,
        )
        return pricelist_price + self.installation_price

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_installation_price_unit()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_installation_sync') and {
                'include_installation', 'installation_price', 'product_id',
                'product_uom_qty', 'price_unit'} & set(vals):
            self._sync_installation_price_unit()
        return res

    def _sync_installation_price_unit(self):
        """Keep price_unit in sync with the installation add-on for lines created/updated
        off-UI (import, API, order duplication) where the form onchange never fires.

        include_installation on  -> price_unit = pricelist price + installation_price
        include_installation off -> if price_unit still carries the add-on, drop it back
                                    to the plain pricelist price (mirrors the uncheck onchange)
        """
        for line in self:
            if not line.product_id or not line.order_id.pricelist_id:
                continue
            base = line.order_id.pricelist_id._get_product_price(
                line.product_id, line.product_uom_qty or 1.0,
                date=line.order_id.date_order,
            )
            if line.include_installation:
                expected = base + line.installation_price
            elif abs(line.price_unit - (base + line.installation_price)) <= 0.001:
                # was priced with installation, checkbox now off -> revert
                expected = base
            else:
                continue
            if abs(line.price_unit - expected) > 0.001:
                line.with_context(skip_installation_sync=True).price_unit = expected

    @api.depends('product_id', 'company_id', 'currency_id', 'product_uom',
                 'order_id.date_order', 'order_id.company_id', 'order_id.pricelist_id',
                 'include_installation', 'install_cost')
    def _compute_standard_cost_purchase_price(self):
        """Extend the Standard Cost Pricelist cost (from buz_sale_pricelist_standard_cost):
        when the line includes installation, add the per-unit installation cost so the
        margin reflects the installation service profit."""
        super()._compute_standard_cost_purchase_price()
        for line in self:
            if line.include_installation and line.install_cost > 0:
                line.standard_cost_price += line.install_cost
                line.purchase_price += line.install_cost

    @api.onchange('include_installation')
    def _onchange_include_installation_toggle(self):
        if not self.product_id or not self.order_id.pricelist_id:
            return

        # Refresh installation cost + purchase_price so margin updates immediately in the UI.
        self._compute_install_cost()
        self._compute_standard_cost_purchase_price()

        # Only handle the "Uncheck" event here to revert to pricelist price.
        # When "Checking", the guard method will handle setting the price.
        if not self.include_installation:
             pricelist_price = self.order_id.pricelist_id._get_product_price(
                 self.product_id, self.product_uom_qty or 1.0,
                 date=self.order_id.date_order
             )
             self.price_unit = pricelist_price

    @api.onchange('include_installation', 'installation_price', 'product_uom_qty', 'product_id', 'price_unit')
    def _onchange_maintain_installation_price(self):
        if not self.product_id or not self.order_id.pricelist_id:
            return

        # If installation is included, we MUST enforce Price = Base + Install
        # This acts as a watchdog against standard Odoo resets (like Qty change)
        if self.include_installation:
             expected_price = self._expected_installation_price_unit()

             if abs(self.price_unit - expected_price) > 0.001:
                 self.price_unit = expected_price
