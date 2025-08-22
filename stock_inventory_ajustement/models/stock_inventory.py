# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.osv import expression
from odoo.tools import float_compare, float_is_zero
import logging
_logger = logging.getLogger(__name__)


READONLY_STATES = {
    "draft": [("readonly", False)],
}




class InventoryAdjustmentsGroup(models.Model):
    _name = "stock.inventory"
    _description = "Inventory Adjustment Group"
    _order = "date desc, id desc"
    _inherit = [
        "mail.thread",
    ]

    name = fields.Char(
        required=True,
        default="Inventory",
        string="Inventory Reference",
        readonly=True,
        states=READONLY_STATES,
    )

    date = fields.Datetime(
        default=lambda self: fields.Datetime.now(),
        readonly=True,
        states=READONLY_STATES,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
        index=True,
        states={"draft": [("readonly", False)]},
        default=lambda self: self.env.company,
        required=True,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ('validation1', 'Première Validation'),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )

    owner_id = fields.Many2one(
        "res.partner",
        "Owner",
        help="This is the owner of the inventory adjustment",
        readonly=True,
        states=READONLY_STATES,
    )

    location_ids = fields.Many2many(
        "stock.location",
        string="Locations",
        domain="[('usage', '=', 'internal'), "
        "'|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        readonly=True,
        states=READONLY_STATES,
    )

    product_selection = fields.Selection(
        [
            ("all", "All Products"),
            ("manual", "Manual Selection"),
            ("category", "Product Category"),
            ("one", "One Product"),
            ("lot", "Lot/Serial Number"),
        ],
        default="all",
        required=True,
        readonly=True,
        states=READONLY_STATES,
    )

    product_ids = fields.Many2many(
        "product.product",
        string="Products",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        readonly=True,
        states=READONLY_STATES,
    )

    start_empty = fields.Boolean('Empty Inventory',
        help="Allows to start with an empty inventory.")

    stock_quant_ids = fields.Many2many(
        "stock.quant",
        string="Inventory Adjustment",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        readonly=True,
        states=READONLY_STATES,
    )

    category_id = fields.Many2one(
        "product.category",
        string="Product Category",
        readonly=True,
        states=READONLY_STATES,
    )

    lot_ids = fields.Many2many(
        "stock.lot",
        string="Lot/Serial Numbers",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        readonly=True,
        states=READONLY_STATES,
    )

    stock_move_ids = fields.One2many(
        "stock.move.line",
        "inventory_adjustment_id",
        string="Inventory Adjustments Done",
        readonly=True,
        states=READONLY_STATES,
    )

    count_stock_quants = fields.Integer(
        compute="_compute_count_stock_quants", string="# Adjustments"
    )

    count_stock_quants_string = fields.Char(
        compute="_compute_count_stock_quants", string="Adjustments"
    )

    count_stock_moves = fields.Integer(
        compute="_compute_count_stock_moves", string="Stock Moves Lines"
    )
    action_state_to_cancel_allowed = fields.Boolean(
        compute="_compute_action_state_to_cancel_allowed"
    )

    exclude_sublocation = fields.Boolean(
        help="If enabled, it will only take into account "
        "the locations selected, and not their children."
    )

    responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Assigned to",
        states={"draft": [("readonly", False)]},
        readonly=True,
        help="Specific responsible of Inventory Adjustment.",
    )

    products_under_review_ids = fields.Many2many(
        comodel_name="product.product",
        compute="_compute_products_under_review_ids",
        search="_search_products_under_review_ids",
        string="Products Under Review",
        relation="stock_inventory_product_review_rel",
    )

    line_ids = fields.One2many(
        'stock.inventory.line', 'inventory_id', string="Ligne d'inventaire",
        copy=False, readonly=False,
        states={'done': [('readonly', True)],'in_progress': [('readonly', True)]})

    prefill_counted_quantity = fields.Selection(string='Counted Quantities',
        help="Allows to start with a pre-filled counted quantity for each lines or "
        "with all counted quantities set to zero.", default='counted',
        selection=[('counted', 'Default to stock on hand'), ('zero', 'Default to zero')])


    package_id = fields.Many2one(
        'stock.quant.package', 'Pack', index=True, check_company=True,
        domain="[('location_id', '=', location_id)]",
    )


    @api.onchange('location_ids','product_ids')
    def _onchange_product_ids(self):
        if self.location_ids:
            # Fetch product IDs available in the selected locations
            quants = self.env['stock.quant'].search([('location_id', 'in', self.location_ids.ids)])
            product_ids = quants.mapped('product_id.id')
            _logger.warning('\n\n _onchange_product_ids ************** product_ids %s \n\n' %(product_ids))

            # Set the domain for product_ids
            return {'domain': {'product_ids': [('id', 'in', product_ids)]}}
        else:
            # No locations selected, allow all products
            return {'domain': {'product_ids': []}}


    def _search_products_under_review_ids(self, operator, value):
        quants = self.env["stock.quant"].search(
            [("to_do", "=", True), ("product_id", operator, value)]
        )
        inventories = quants.mapped("stock_inventory_ids")
        return [("id", "in", inventories.ids), ("state", "=", "in_progress")]

    @api.depends("stock_quant_ids", "stock_quant_ids.to_do", "state")
    def _compute_products_under_review_ids(self):
        for record in self:
            if record.state == "in_progress":
                products = record.stock_quant_ids.filtered(
                    lambda quant: quant.to_do
                ).mapped("product_id")
                record.products_under_review_ids = (
                    [(6, 0, products.ids)] if products else [(5, 0, 0)]
                )
            else:
                record.products_under_review_ids = [(5, 0, 0)]

    @api.depends("stock_quant_ids","state")
    def _compute_count_stock_quants(self):
        for rec in self:
            current_inventory_id = rec.id
            quants = rec.stock_quant_ids
            quants_to_do = quants.filtered(lambda q: q.to_do)
            quants_pending_to_review = [
                q
                for q in quants_to_do
                if q.current_inventory_id.id == current_inventory_id
            ]
            count_pending_to_review = len(quants_pending_to_review)
            rec.count_stock_quants = len(quants)
            rec.count_stock_quants_string = "{} / {}".format(
                count_pending_to_review, rec.count_stock_quants
            )

    @api.depends("stock_move_ids")
    def _compute_count_stock_moves(self):
        group_fname = "inventory_adjustment_id"
        group_data = self.env["stock.move.line"].read_group(
            [
                (group_fname, "in", self.ids),
            ],
            [group_fname],
            [group_fname],
        )
        data_by_adj_id = {
            row[group_fname][0]: row.get(f"{group_fname}_count", 0)
            for row in group_data
        }
        for rec in self:
            rec.count_stock_moves = data_by_adj_id.get(rec.id, 0)

    def _compute_action_state_to_cancel_allowed(self):
        for rec in self:
            rec.action_state_to_cancel_allowed = rec.state == "draft"

    def _get_quants(self, locations):
        self.ensure_one()
        domain = []
        base_domain = self._get_base_domain(locations)
        if self.product_selection == "all":
            domain = self._get_domain_all_quants(base_domain)
        elif self.product_selection == "manual":
            domain = self._get_domain_manual_quants(base_domain)
        elif self.product_selection == "one":
            domain = self._get_domain_one_quant(base_domain)
        elif self.product_selection == "lot":
            domain = self._get_domain_lot_quants(base_domain)
        elif self.product_selection == "category":
            domain = self._get_domain_category_quants(base_domain)
        return self.env["stock.quant"].search(domain)

    def _get_base_domain(self, locations):
        return (
            [
                ("location_id", "in", locations.mapped("id")),
            ]
            if self.exclude_sublocation
            else [
                ("location_id", "child_of", locations.child_internal_location_ids.ids),
            ]
        )

    def _get_domain_all_quants(self, base_domain):
        return base_domain

    def _get_domain_manual_quants(self, base_domain):
        self.ensure_one()
        return expression.AND(
            [base_domain, [("product_id", "in", self.product_ids.ids)]]
        )

    def _get_domain_one_quant(self, base_domain):
        self.ensure_one()
        return expression.AND(
            [
                base_domain,
                [
                    ("product_id", "in", self.product_ids.ids),
                ],
            ]
        )

    def _get_domain_lot_quants(self, base_domain):
        self.ensure_one()
        return expression.AND(
            [
                base_domain,
                [
                    ("product_id", "in", self.product_ids.ids),
                    ("lot_id", "in", self.lot_ids.ids),
                ],
            ]
        )

    def _get_domain_category_quants(self, base_domain):
        self.ensure_one()
        return expression.AND(
            [
                base_domain,
                [
                    "|",
                    ("product_id.categ_id", "=", self.category_id.id),
                    ("product_id.categ_id", "in", self.category_id.child_id.ids),
                ],
            ]
        )

    def refresh_stock_quant_ids(self):
        for rec in self:
            rec.stock_quant_ids = rec._get_quants(rec.location_ids)

    def _get_quant_joined_names(self, quants, field):
        return ", ".join(quants.mapped(f"{field}.display_name"))

    def action_state_to_in_progress(self):
        self.ensure_one()
        search_filter = [
            (
                "location_id",
                "child_of" if not self.exclude_sublocation else "in",
                self.location_ids.ids,
            ),
            ("to_do", "=", True),
        ]

        if self.product_ids:
            search_filter.append(("product_id", "in", self.product_ids.ids))
            error_field = "product_id"
            error_message = _(
                "There are active adjustments for the requested products: %(names)s. "
                "Blocking adjustments: %(blocking_names)s"
            )
        else:
            error_field = "location_id"
            error_message = _(
                "There's already an Adjustment in Process "
                "using one requested Location: %(names)s. "
                "Blocking adjustments: %(blocking_names)s"
            )

        quants = self.env["stock.quant"].search(search_filter)
        if quants:
            inventory_ids = self.env["stock.inventory"].search(
                [("stock_quant_ids", "in", quants.ids), ("state", "=", "in_progress")]
            )
            if inventory_ids:
                blocking_names = ", ".join(inventory_ids.mapped("name"))
                names = self._get_quant_joined_names(quants, error_field)
                raise ValidationError(
                    error_message % {"names": names, "blocking_names": blocking_names}
                )

        """
        Custom code to transfer inventory line data to stock.quant and apply the inventory adjustment.
        """
        for inventory in self:
            quant_data = []  # List to hold data for batch creation

            # Loop through all inventory lines
            quant_ids = []
            for line in inventory.line_ids:
                product = line.product_id
                location = line.location_id
                lot_id = line.prod_lot_id  # If applicable
                quantity = line.product_qty

                # Search for the corresponding quant
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id),
                    ('lot_id', '=', lot_id.id if lot_id else False),
                ], limit=1)

                if quant:
                    # _logger.warning('action_state_to_in_progress ************** quant.todo 000000 =  %s' %(quant.to_do))
                    quant.inventory_quantity = quantity
                    quant.to_do = True
                    quant.current_inventory_id = self.id
                    quant.inventory_date = self.date
                    _logger.warning('\n\n action_state_to_in_progress ************** quant.todo 22222 =  %s \n\n' %(quant.ids))
                    quant_ids.append(quant.id)
                    
                else:
                    # Prepare data for new quant
                    quant_data.append({
                        'product_id': product.id,
                        'location_id': location.id,
                        'lot_id': lot_id.id if lot_id else False,
                        'quantity': quantity,
                        'to_do' : True,
                        'current_inventory_id' : self.id,
                        'inventory_date' : self.date,
                    })

            # Batch create new quants
            if quant_ids:
                self.write({"stock_quant_ids": [(6, 0, quant_ids)]})
            if quant_data:
                self.env['stock.quant'].create(quant_data)

        return self.write({"state": "in_progress"})

    def action_state_to_done(self):
        self.ensure_one()
        self.state = "done"
        self.stock_quant_ids.filtered(
            lambda q: q.current_inventory_id.id == self.id
        ).action_apply_inventory()
        self.stock_quant_ids.filtered(
            lambda q: q.current_inventory_id.id == self.id
        ).update(
            {
                "to_do": False,
                "user_id": False,
                "inventory_date": False,
                "current_inventory_id": False,
            }
        )
        return

    def action_auto_state_to_done(self):
        self.ensure_one()
        if not any(self.stock_quant_ids.filtered(lambda sq: sq.to_do)):
            self.action_state_to_done()
            self.to_do = False
            self.user_id = False
            self.inventory_date = False
            self.current_inventory_id = False
        return

    def action_state_to_draft(self):
        self.ensure_one()
        self.state = "draft"
        self.stock_quant_ids.filtered(lambda q: q.current_inventory_id.id == self.id).action_clear_inventory_quantity()
        self.stock_quant_ids.filtered(
            lambda q: q.current_inventory_id.id == self.id
        ).update({
                "to_do": False,
                "user_id": False,
                "inventory_date": False,
                "current_inventory_id": False,
            })
        self.stock_quant_ids = None
        self.line_ids = None
        return

    def action_state_to_cancel(self):
        self.ensure_one()
        self._check_action_state_to_cancel()
        self.write(
            {
                "state": "cancel",
            }
        )

    def _check_action_state_to_cancel(self):
        for rec in self:
            if not rec.action_state_to_cancel_allowed:
                raise UserError(
                    _(
                        "You can't cancel this inventory %(display_name)s.",
                        display_name=rec.display_name,
                    )
                )

    def action_view_inventory_adjustment(self):
        self.ensure_one()
        result = self.env["stock.quant"].action_view_inventory()
        context = result.get("context", {})
        context.update(
            {
                "search_default_to_do": 1,
                "inventory_id": self.id,
                "default_to_do": True,
            }
        )
        result.update(
            {
                "domain": [
                    ("id", "in", self.stock_quant_ids.ids),
                    ("current_inventory_id", "=", self.id),
                ],
                "search_view_id": self.env.ref("stock.quant_search_view").id,
                "context": context,
            }
        )
        return result

    def action_view_stock_moves(self):
        self.ensure_one()
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_inventory.action_view_stock_move_line_inventory_tree"
        )
        result["domain"] = [("inventory_adjustment_id", "=", self.id)]
        result["context"] = {}
        return result

    def _check_inventory_in_progress_not_override(self):
        for rec in self:
            if rec.state == "in_progress":
                location_condition = [
                    (
                        "location_ids",
                        "child_of" if not rec.exclude_sublocation else "in",
                        rec.location_ids.ids,
                    )
                ]
                if rec.product_ids:
                    product_condition = [
                        ("state", "=", "in_progress"),
                        ("id", "!=", rec.id),
                        ("product_ids", "in", rec.product_ids.ids),
                    ] + location_condition
                    inventories = self.search(product_condition)
                else:
                    inventories = self.search(
                        [("state", "=", "in_progress"), ("id", "!=", rec.id)]
                        + location_condition
                    )
                for inventory in inventories:
                    if any(
                        i in inventory.location_ids.ids for i in rec.location_ids.ids
                    ):
                        raise ValidationError(
                            _(
                                "Cannot have more than one in-progress inventory "
                                "adjustment affecting the same location or product "
                                "at the same time."
                            )
                        )

    @api.constrains("product_selection", "product_ids")
    def _check_one_product_in_product_selection(self):
        for rec in self:
            if len(rec.product_ids) > 1:
                if rec.product_selection == "one":
                    raise ValidationError(
                        _(
                            "When 'Product Selection: One Product' is selected"
                            " you are only able to add one product."
                        )
                    )
                elif rec.product_selection == "lot":
                    raise ValidationError(
                        _(
                            "When 'Product Selection: Lot Serial Number' is selected"
                            " you are only able to add one product."
                        )
                    )



    def unlink(self):
        for adjustment in self:
            if adjustment.state not in ('draft', 'cancel'):
                raise UserError(
                    _(
                        "You can only delete inventory adjustments groups in"
                        " Draft/Cancel state."
                    )
                )
        return super().unlink()



    ######################################
    ######################################
    ######################################

    def action_start(self):
        self.ensure_one()
        self._action_start()
        return True

    def _action_start(self):
        """ Confirms the Inventory Adjustment and generates its inventory lines
        if its state is draft and don't have already inventory lines (can happen
        with demo data or tests).
        """
        for inventory in self:
            if inventory.state != 'draft':
                continue
            vals = {
                'state': 'validation1',
                'date': fields.Datetime.now()
            }
            if not inventory.line_ids and not inventory.start_empty:
                self.env['stock.inventory.line'].create(inventory._get_inventory_lines_values())
            inventory.write(vals)

    def _get_inventory_lines_values(self):
        """Return the values of the inventory lines to create for this inventory.

        :return: a list containing the `stock.inventory.line` values to create
        :rtype: list
        """
        self.ensure_one()
        quants_groups = self._get_quantities()
        vals = []
        for (product_id, location_id, lot_id, package_id, owner_id), quantity in quants_groups.items():
            line_values = {
                'inventory_id': self.id,
                'product_qty': 0 if self.prefill_counted_quantity == "zero" else quantity,
                'theoretical_qty': quantity,
                'prod_lot_id': lot_id,
                'partner_id': owner_id,
                'product_id': product_id,
                'location_id': location_id,
                'package_id': package_id
            }
            line_values['product_uom_id'] = self.env['product.product'].browse(product_id).uom_id.id
            vals.append(line_values)
        
        return vals


    def _get_quantities(self):
        """Return quantities group by product_id, location_id, lot_id, package_id and owner_id

        :return: a dict with keys as tuple of group by and quantity as value
        :rtype: dict
        """
        self.ensure_one()
        if self.location_ids:
            domain_loc = [('id', 'child_of', self.location_ids.ids)]
        else:
            domain_loc = [('company_id', '=', self.company_id.id), ('usage', 'in', ['internal', 'transit'])]
        locations_ids = [l['id'] for l in self.env['stock.location'].search_read(domain_loc, ['id'])]

        domain = [('company_id', '=', self.company_id.id),
                  ('quantity', '!=', '0'),
                  ('location_id', 'in', locations_ids)]
        if self.prefill_counted_quantity == 'zero':
            domain.append(('product_id.active', '=', True))

        if self.product_ids:
            domain = expression.AND([domain, [('product_id', 'in', self.product_ids.ids)]])

        fields = ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id', 'quantity:sum']
        group_by = ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id']

        quants = self.env['stock.quant'].read_group(domain, fields, group_by, lazy=False)
        return {(
            quant['product_id'] and quant['product_id'][0] or False,
            quant['location_id'] and quant['location_id'][0] or False,
            quant['lot_id'] and quant['lot_id'][0] or False,
            quant['package_id'] and quant['package_id'][0] or False,
            quant['owner_id'] and quant['owner_id'][0] or False):
            quant['quantity'] for quant in quants
        }



class InventoryAdjustmentsLine(models.Model):
    _name = "stock.inventory.line"
    _description = "Inventory Line"
    _order = "product_id, inventory_id, location_id, prod_lot_id"
    _inherit = ["mail.thread"]


    @api.model
    def _domain_location_id(self):
        if self.env.context.get('active_model') == 'stock.inventory':
            inventory = self.env['stock.inventory'].browse(self.env.context.get('active_id'))
            if inventory.exists() and inventory.location_ids:
                return "[('company_id', '=', company_id), ('usage', 'in', ['internal', 'transit']), ('id', 'child_of', %s)]" % inventory.location_ids.ids
        return "[('company_id', '=', company_id), ('usage', 'in', ['internal', 'transit'])]"

    @api.model
    def _domain_product_id(self):
        if self.env.context.get('active_model') == 'stock.inventory':
            inventory = self.env['stock.inventory'].browse(self.env.context.get('active_id'))
            if inventory.exists() and len(inventory.product_ids) > 1:
                return "[('type', '=', 'product'), '|', ('company_id', '=', False), ('company_id', '=', company_id), ('id', 'in', %s)]" % inventory.product_ids.ids
        return "[('type', '=', 'product'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]"




    inventory_id = fields.Many2one('stock.inventory', 'Inventaire', ondelete='cascade')

    line_date = fields.Datetime(
        related="inventory_id.date",
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company', 'Company', related='inventory_id.company_id',
        index=True, readonly=True, store=True)

    state = fields.Selection(string='État', related='inventory_id.state')

    location_id = fields.Many2one(
        'stock.location', 'Location', check_company=True,
        domain=lambda self: self._domain_location_id(),

        index=True, required=True)

    package_id = fields.Many2one(
        'stock.quant.package', 'Pack', index=True, check_company=True,
        domain="[('location_id', '=', location_id)]",
    )

    product_id = fields.Many2one(
        'product.product', 'Product', check_company=True,
        domain=lambda self: self._domain_product_id(),
        index=True, required=True)

    product_uom_id = fields.Many2one(
        'uom.uom', 'Product Unit of Measure',
        required=True, readonly=True)

    product_qty = fields.Float(
        'Counted Quantity',
        readonly=False,
        digits='Product Unit of Measure', default=0)
    categ_id = fields.Many2one(related='product_id.categ_id', store=True)

    prod_lot_id = fields.Many2one(
        'stock.lot', 'Lot/Numéro de série', check_company=True,
        domain="[('product_id','=',product_id), ('company_id', '=', company_id)]")

    partner_id = fields.Many2one('res.partner', 'Owner', check_company=True)

    theoretical_qty = fields.Float('Theoretical Quantity',digits='Product Unit of Measure', readonly=True)

    difference_qty = fields.Float('Difference', compute='_compute_difference', readonly=True, digits='Product Unit of Measure',
        search="_search_difference_qty",
        help="Indicates the gap between the product's theoretical quantity and its newest quantity.",)

    inventory_date = fields.Datetime('Inventory Date', readonly=True,
        default=fields.Datetime.now,
        help="Last date at which the On Hand Quantity has been computed.")





    @api.depends('product_qty', 'theoretical_qty')
    def _compute_difference(self):
        for line in self:
            line.difference_qty = line.product_qty - line.theoretical_qty


    @api.onchange('product_id', 'location_id', 'product_uom_id', 'prod_lot_id', 'partner_id', 'package_id')
    def _onchange_quantity_context(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
        if self.product_id and self.location_id and self.product_id.uom_id.category_id == self.product_uom_id.category_id:  # TDE FIXME: last part added because crash
            # theoretical_qty = self.product_id.get_theoretical_quantity(
            #     self.product_id.id,
            #     self.location_id.id,
            #     lot_id=self.prod_lot_id.id,
            #     package_id=self.package_id.id,
            #     owner_id=self.partner_id.id,
            #     to_uom=self.product_uom_id.id,
            # )
            quant_ids =  self.env['stock.quant'].search([
                ('product_id','=',self.product_id.id),
                ('location_id', '=', self.location_id.id),
                ('lot_id', '=', self.prod_lot_id.id),
                ('package_id', '=', self.package_id.id),                
                ('product_uom_id', '=', self.product_uom_id.id),                
                ])
            theoretical_qty = sum(quant_ids.mapped('quantity'))
            _logger.warning('\n\n _onchange_quantity_context 0000000 ************** theoretical_qty == %s \n\n' %(theoretical_qty))
        else:
            theoretical_qty = 0
        # Sanity check on the lot.
        if self.prod_lot_id:
            if self.product_id.tracking == 'none' or self.product_id != self.prod_lot_id.product_id:
                self.prod_lot_id = False

        if self.prod_lot_id and self.product_id.tracking == 'serial':
            # We force `product_qty` to 1 for SN tracked product because it's
            # the only relevant value aside 0 for this kind of product.
            self.product_qty = 1
        elif self.product_id and float_compare(self.product_qty, self.theoretical_qty, precision_rounding=self.product_uom_id.rounding) == 0:
            # We update `product_qty` only if it equals to `theoretical_qty` to
            # avoid to reset quantity when user manually set it.
            self.product_qty = theoretical_qty
        _logger.warning('\n\n _onchange_quantity_context 11111 ************** theoretical_qty == %s \n\n' %(theoretical_qty))
        self.theoretical_qty = theoretical_qty

    @api.model_create_multi
    def create(self, vals_list):
        """ Override to handle the case we create inventory line without
        `theoretical_qty` because this field is usually computed, but in some
        case (typicaly in tests), we create inventory line without trigger the
        onchange, so in this case, we set `theoretical_qty` depending of the
        product's theoretical quantity.
        Handles the same problem with `product_uom_id` as this field is normally
        set in an onchange of `product_id`.
        Finally, this override checks we don't try to create a duplicated line.
        """
        for values in vals_list:
            if not values['location_id']:
                raise ValidationError("Vous devez insérer la localisation")
            # if 'theoretical_qty' not in values:
            #     quant_ids =  self.env['stock.quant'].search([
            #     ('product_id','=',self.product_id.id),
            #     ('location_id', '=', self.location_id.id),
            #     ('lot_id', '=', self.prod_lot_id.id),
            #     ('package_id', '=', self.package_id.id),                
            #     ('product_uom_id', '=', self.product_uom_id.id),                
            #     ])
            #     theoretical_qty = sum(quant_ids.mapped('quantity'))
            #     _logger.warning('\n\n create xxxxxxxxxxx ************** theoretical_qty == %s \n\n' %(theoretical_qty))
            #     values['theoretical_qty'] = theoretical_qty
            if 'product_id' in values and 'product_uom_id' not in values:
                values['product_uom_id'] = self.env['product.product'].browse(values['product_id']).uom_id.id

        res = super(InventoryAdjustmentsLine, self).create(vals_list)
        res._check_no_duplicate_line()
        return res


    def write(self, vals):
        res = super(InventoryAdjustmentsLine, self).write(vals)
        self._check_no_duplicate_line()
        return res

    def _check_no_duplicate_line(self):
        for line in self:
            domain = [
                ('id', '!=', line.id),
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', line.location_id.id),
                ('partner_id', '=', line.partner_id.id),
                ('package_id', '=', line.package_id.id),
                ('prod_lot_id', '=', line.prod_lot_id.id),
                ('inventory_id', '=', line.inventory_id.id)]
            existings = self.search_count(domain)
            if existings:
                raise UserError(_("There is already one inventory adjustment line for this product,"
                                  " you should rather modify this one instead of creating a new one."))

    @api.constrains('product_id')
    def _check_product_id(self):
        """ As no quants are created for consumable products, it should not be possible do adjust
        their quantity.
        """
        for line in self:
            if line.product_id.type != 'product':
                raise ValidationError(_("You can only adjust storable products.") + '\n\n%s -> %s' % (line.product_id.display_name, line.product_id.type))

    def _search_difference_qty(self, operator, value):
        if operator == '=':
            result = True
        elif operator == '!=':
            result = False
        else:
            raise NotImplementedError()
        lines = self.search([('inventory_id', '=', self.env.context.get('default_inventory_id'))])
        line_ids = lines.filtered(lambda line: float_is_zero(line.difference_qty, line.product_id.uom_id.rounding) == result).ids
        return [('id', 'in', line_ids)]
