from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_round


class MogenSopRecommendation(models.Model):
    _inherit = "mogen.sop.recommendation"

    sop_supplier_id = fields.Many2one("res.partner", check_company=True)


class MogenSopPurchasePlan(models.Model):
    _name = "mogen.sop.purchase.plan"
    _description = "S&OP Purchase Plan"
    _order = "date_start desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default="New")
    sop_plan_id = fields.Many2one("mogen.sop.plan", required=True, check_company=True, ondelete="restrict", index=True)
    version_id = fields.Many2one("mogen.sop.plan.version", index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True, index=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    state = fields.Selection([("draft", "Draft"), ("calculated", "Calculated"), ("review", "Review"), ("approved", "Approved"), ("executed", "Executed"), ("cancelled", "Cancelled")], default="draft", required=True)
    line_ids = fields.One2many("mogen.sop.purchase.line", "purchase_plan_id")
    total_purchase_qty = fields.Float(compute="_compute_totals", store=True)
    total_purchase_value = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    supplier_count = fields.Integer(compute="_compute_totals", store=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    supplier_strategy = fields.Selection([("preferred_supplier", "Preferred Supplier"), ("lowest_price", "Lowest Price"), ("shortest_lead_time", "Shortest Lead Time"), ("balanced", "Balanced")], required=True, default="preferred_supplier")
    note = fields.Text()

    @api.depends("line_ids.proposed_qty", "line_ids.subtotal", "line_ids.supplier_id")
    def _compute_totals(self):
        for plan in self:
            plan.total_purchase_qty = sum(plan.line_ids.mapped("proposed_qty"))
            plan.total_purchase_value = sum(plan.line_ids.mapped("subtotal"))
            plan.supplier_count = len(plan.line_ids.mapped("supplier_id"))

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        if any(plan.date_start > plan.date_end for plan in self):
            raise ValidationError(_("The purchase-plan end date must not precede its start date."))

    def _supplierinfo_for(self, product, explicit_supplier=False):
        infos = self.env["product.supplierinfo"].sudo().search([
            ("product_tmpl_id", "=", product.product_tmpl_id.id),
            ("company_id", "in", (False, self.company_id.id)),
        ], order="sequence, min_qty, id")
        if explicit_supplier:
            infos = infos.filtered(lambda info: info.partner_id == explicit_supplier)
        if not infos:
            return self.env["product.supplierinfo"]
        if self.supplier_strategy == "lowest_price":
            return infos.sorted(key=lambda info: (info.price, info.sequence, info.id))[0]
        if self.supplier_strategy == "shortest_lead_time":
            return infos.sorted(key=lambda info: (info.delay, info.sequence, info.id))[0]
        if self.supplier_strategy == "balanced":
            return infos.sorted(key=lambda info: (info.delay, info.price, info.sequence, info.id))[0]
        return infos[0]

    def _round_purchase_qty(self, quantity, supplierinfo, product):
        supplier_uom = supplierinfo.product_uom or product.uom_id
        minimum = supplier_uom._compute_quantity(supplierinfo.min_qty, product.uom_id, round=False)
        multiple = minimum if supplierinfo.min_qty else product.uom_id.rounding
        rounded = max(quantity, minimum)
        return float_round(rounded, precision_rounding=multiple or product.uom_id.rounding, rounding_method="UP")

    def action_calculate_purchase(self):
        for plan in self:
            if plan.state not in ("draft", "calculated"):
                raise UserError(_("Only draft or calculated purchase plans can be recalculated."))
            recommendations = self.env["mogen.sop.recommendation"].sudo().search([
                ("plan_id", "=", plan.sop_plan_id.id), ("company_id", "=", plan.company_id.id),
                ("warehouse_id", "=", plan.warehouse_id.id), ("recommendation_type", "=", "purchase"),
                ("state", "=", "approved"), ("required_date", ">=", plan.date_start), ("required_date", "<=", plan.date_end),
            ])
            values = []
            for recommendation in recommendations:
                info = plan._supplierinfo_for(recommendation.product_id, recommendation.sop_supplier_id)
                if not info:
                    continue
                proposed = plan._round_purchase_qty(recommendation.quantity, info, recommendation.product_id)
                supplier_currency = info.currency_id or info.partner_id.property_purchase_currency_id or plan.company_id.currency_id
                unit_price = supplier_currency._convert(info.price, plan.currency_id, plan.company_id, fields.Date.today())
                required_date = recommendation.required_date
                order_date = required_date - timedelta(days=info.delay or 0)
                values.append({"purchase_plan_id": plan.id, "recommendation_id": recommendation.id, "company_id": plan.company_id.id, "warehouse_id": plan.warehouse_id.id, "product_id": recommendation.product_id.id, "supplier_id": info.partner_id.id, "supplierinfo_id": info.id, "required_qty": recommendation.quantity, "proposed_qty": proposed, "minimum_qty": info.product_uom._compute_quantity(info.min_qty, recommendation.product_id.uom_id, round=False) if info.product_uom else info.min_qty, "purchase_multiple": info.product_uom._compute_quantity(info.min_qty, recommendation.product_id.uom_id, round=False) if info.min_qty and info.product_uom else recommendation.product_id.uom_id.rounding, "unit_price": unit_price, "currency_id": plan.currency_id.id, "supplier_lead_time": info.delay, "required_date": required_date, "planned_order_date": order_date, "expected_arrival_date": required_date, "price_status": "valid", "lead_time_status": "valid"})
            plan.line_ids.sudo().unlink()
            self.env["mogen.sop.purchase.line"].sudo().create(values)
            plan.state = "calculated"
        return True

    def action_create_draft_pos(self):
        for plan in self:
            if plan.state not in ("calculated", "review", "approved"):
                raise UserError(_("Calculate the purchase plan before creating draft purchase orders."))
            groups = defaultdict(lambda: self.env["mogen.sop.purchase.line"])
            for line in plan.line_ids.filtered(lambda item: not item.generated_po_id):
                picking_type = line.warehouse_id.in_type_id
                groups[(line.company_id.id, line.supplier_id.id, line.currency_id.id, line.warehouse_id.id, picking_type.id)] |= line
            for key, lines in groups.items():
                company_id, supplier_id, currency_id, warehouse_id, picking_type_id = key
                order = self.env["purchase.order"].sudo().create({"partner_id": supplier_id, "company_id": company_id, "currency_id": currency_id, "picking_type_id": picking_type_id, "sop_plan_id": plan.sop_plan_id.id, "sop_version_id": plan.version_id.id, "sop_purchase_plan_id": plan.id, "sop_destination_warehouse_id": warehouse_id})
                for line in lines:
                    po_line = self.env["purchase.order.line"].sudo().create({"order_id": order.id, "product_id": line.product_id.id, "product_qty": line.proposed_qty, "product_uom": line.product_id.uom_id.id, "price_unit": line.unit_price, "date_planned": fields.Datetime.to_datetime(line.expected_arrival_date), "sop_plan_id": plan.sop_plan_id.id, "sop_purchase_plan_id": plan.id, "sop_purchase_line_id": line.id})
                    line.sudo().write({"generated_po_id": order.id, "generated_po_line_id": po_line.id, "state": "generated"})
        return True


class MogenSopPurchaseLine(models.Model):
    _name = "mogen.sop.purchase.line"
    _description = "S&OP Purchase Plan Line"
    _order = "required_date, product_id"
    _check_company_auto = True
    purchase_plan_id = fields.Many2one("mogen.sop.purchase.plan", required=True, ondelete="cascade", index=True)
    recommendation_id = fields.Many2one("mogen.sop.recommendation", required=True, check_company=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    supplier_id = fields.Many2one("res.partner", required=True, check_company=True)
    supplierinfo_id = fields.Many2one("product.supplierinfo", required=True)
    required_qty = fields.Float(required=True, readonly=True); proposed_qty = fields.Float(required=True, readonly=True); minimum_qty = fields.Float(readonly=True); purchase_multiple = fields.Float(readonly=True)
    unit_price = fields.Monetary(required=True, readonly=True, currency_field="currency_id"); currency_id = fields.Many2one("res.currency", required=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True, currency_field="currency_id")
    supplier_lead_time = fields.Integer(readonly=True); required_date = fields.Date(required=True); planned_order_date = fields.Date(required=True); expected_arrival_date = fields.Date(required=True)
    price_status = fields.Selection([("valid", "Valid"), ("missing", "Missing")], required=True); lead_time_status = fields.Selection([("valid", "Valid"), ("risk", "Risk")], required=True)
    generated_po_id = fields.Many2one("purchase.order", readonly=True, copy=False, check_company=True); generated_po_line_id = fields.Many2one("purchase.order.line", readonly=True, copy=False, check_company=True)
    state = fields.Selection([("draft", "Draft"), ("generated", "Generated")], default="draft", required=True)
    _sql_constraints = [("unique_plan_recommendation", "unique(purchase_plan_id, recommendation_id)", "A recommendation can only appear once in a purchase plan.")]
    @api.depends("proposed_qty", "unit_price")
    def _compute_subtotal(self):
        for line in self: line.subtotal = line.proposed_qty * line.unit_price


class MogenSopTransferPlan(models.Model):
    _name = "mogen.sop.transfer.plan"; _description = "S&OP Transfer Plan"; _check_company_auto = True
    name = fields.Char(required=True, default="New"); sop_plan_id = fields.Many2one("mogen.sop.plan", required=True, check_company=True); version_id = fields.Many2one("mogen.sop.plan.version")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company); destination_warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True)
    state = fields.Selection([("draft", "Draft"), ("calculated", "Calculated"), ("generated", "Generated"), ("cancelled", "Cancelled")], default="draft", required=True); line_ids = fields.One2many("mogen.sop.transfer.line", "transfer_plan_id"); total_transfer_qty = fields.Float(compute="_compute_total", store=True)
    @api.depends("line_ids.proposed_qty")
    def _compute_total(self):
        for plan in self: plan.total_transfer_qty = sum(plan.line_ids.mapped("proposed_qty"))
    def action_calculate_transfers(self):
        for plan in self:
            recommendations = self.env["mogen.sop.recommendation"].sudo().search([("plan_id", "=", plan.sop_plan_id.id), ("company_id", "=", plan.company_id.id), ("warehouse_id", "=", plan.destination_warehouse_id.id), ("recommendation_type", "=", "transfer"), ("state", "=", "approved")])
            warehouses = self.env["stock.warehouse"].sudo().search([("company_id", "=", plan.company_id.id), ("id", "!=", plan.destination_warehouse_id.id)])
            products = recommendations.mapped("product_id")
            quants = self.env["stock.quant"].sudo().read_group([("company_id", "=", plan.company_id.id), ("product_id", "in", products.ids), ("location_id", "in", warehouses.mapped("lot_stock_id").ids)], ["product_id", "location_id", "quantity:sum", "reserved_quantity:sum"], ["product_id", "location_id"], lazy=False)
            free = {(row["product_id"][0], row["location_id"][0]): row.get("quantity", 0.0)-row.get("reserved_quantity", 0.0) for row in quants if row.get("product_id") and row.get("location_id")}
            orderpoints = self.env["stock.warehouse.orderpoint"].sudo().search([("warehouse_id", "in", warehouses.ids), ("product_id", "in", products.ids), ("active", "=", True)])
            safety = defaultdict(float)
            for op in orderpoints: safety[(op.warehouse_id.id, op.product_id.id)] += op.product_min_qty
            values=[]
            for rec in recommendations:
                choices=[]
                for wh in warehouses:
                    surplus=max(0.0, free.get((rec.product_id.id, wh.lot_stock_id.id),0.0)-safety[(wh.id,rec.product_id.id)])
                    if surplus: choices.append((surplus,wh))
                if not choices: continue
                surplus, source=max(choices,key=lambda item:(item[0],-item[1].id)); qty=min(surplus,rec.quantity)
                values.append({"transfer_plan_id":plan.id,"recommendation_id":rec.id,"company_id":plan.company_id.id,"product_id":rec.product_id.id,"source_warehouse_id":source.id,"destination_warehouse_id":plan.destination_warehouse_id.id,"source_free_qty":free.get((rec.product_id.id,source.lot_stock_id.id),0.0),"destination_shortage_qty":rec.quantity,"safety_stock_after_transfer":safety[(source.id,rec.product_id.id)],"proposed_qty":qty,"required_date":rec.required_date})
            plan.line_ids.sudo().unlink(); self.env["mogen.sop.transfer.line"].sudo().create(values); plan.state="calculated"
        return True
    def action_create_draft_pickings(self):
        for plan in self:
            for line in plan.line_ids.filtered(lambda item:not item.generated_picking_id):
                picking_type=line.source_warehouse_id.int_type_id
                picking=self.env["stock.picking"].sudo().create({"picking_type_id":picking_type.id,"location_id":line.source_warehouse_id.lot_stock_id.id,"location_dest_id":line.destination_warehouse_id.lot_stock_id.id,"company_id":plan.company_id.id,"sop_plan_id":plan.sop_plan_id.id,"sop_version_id":plan.version_id.id,"sop_transfer_plan_id":plan.id,"sop_transfer_line_id":line.id})
                self.env["stock.move"].sudo().create({"name":line.product_id.display_name,"product_id":line.product_id.id,"product_uom_qty":line.proposed_qty,"product_uom":line.product_id.uom_id.id,"picking_id":picking.id,"location_id":picking.location_id.id,"location_dest_id":picking.location_dest_id.id,"company_id":plan.company_id.id,"sop_plan_id":plan.sop_plan_id.id,"sop_transfer_plan_id":plan.id,"sop_transfer_line_id":line.id})
                line.sudo().write({"generated_picking_id":picking.id,"state":"generated"})
            plan.state="generated"
        return True


class MogenSopTransferLine(models.Model):
    _name="mogen.sop.transfer.line"; _description="S&OP Transfer Plan Line"; _check_company_auto=True
    transfer_plan_id=fields.Many2one("mogen.sop.transfer.plan",required=True,ondelete="cascade"); recommendation_id=fields.Many2one("mogen.sop.recommendation",required=True,check_company=True); company_id=fields.Many2one("res.company",required=True); product_id=fields.Many2one("product.product",required=True,check_company=True); source_warehouse_id=fields.Many2one("stock.warehouse",required=True,check_company=True); destination_warehouse_id=fields.Many2one("stock.warehouse",required=True,check_company=True); source_free_qty=fields.Float(readonly=True); destination_shortage_qty=fields.Float(readonly=True); safety_stock_after_transfer=fields.Float(readonly=True); proposed_qty=fields.Float(required=True,readonly=True); required_date=fields.Date(required=True); generated_picking_id=fields.Many2one("stock.picking",readonly=True,copy=False,check_company=True); state=fields.Selection([("draft","Draft"),("generated","Generated")],default="draft",required=True)
    _sql_constraints=[("unique_plan_recommendation","unique(transfer_plan_id,recommendation_id)","A recommendation can only appear once in a transfer plan."),("different_warehouses","check(source_warehouse_id != destination_warehouse_id)","Source and destination warehouses must differ.")]


class PurchaseOrder(models.Model):
    _inherit="purchase.order"
    sop_plan_id=fields.Many2one("mogen.sop.plan",copy=False,index=True); sop_version_id=fields.Many2one("mogen.sop.plan.version",copy=False); sop_purchase_plan_id=fields.Many2one("mogen.sop.purchase.plan",copy=False,index=True); sop_destination_warehouse_id=fields.Many2one("stock.warehouse",copy=False,check_company=True)
class PurchaseOrderLine(models.Model):
    _inherit="purchase.order.line"
    sop_plan_id=fields.Many2one("mogen.sop.plan",copy=False,index=True); sop_purchase_plan_id=fields.Many2one("mogen.sop.purchase.plan",copy=False); sop_purchase_line_id=fields.Many2one("mogen.sop.purchase.line",copy=False,index=True)
class StockPicking(models.Model):
    _inherit="stock.picking"
    sop_plan_id=fields.Many2one("mogen.sop.plan",copy=False,index=True); sop_version_id=fields.Many2one("mogen.sop.plan.version",copy=False); sop_transfer_plan_id=fields.Many2one("mogen.sop.transfer.plan",copy=False,index=True); sop_transfer_line_id=fields.Many2one("mogen.sop.transfer.line",copy=False,index=True)
class StockMove(models.Model):
    _inherit="stock.move"
    sop_plan_id=fields.Many2one("mogen.sop.plan",copy=False,index=True); sop_transfer_plan_id=fields.Many2one("mogen.sop.transfer.plan",copy=False); sop_transfer_line_id=fields.Many2one("mogen.sop.transfer.line",copy=False,index=True)
