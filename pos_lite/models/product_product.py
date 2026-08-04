from odoo import api, fields, models


def _kit_stock_map(env, location_id, exclude_product_ids):
    """Return {product_id: buildable_qty} for BOM-kit products buildable at
    location_id, excluding products in exclude_product_ids (already have
    their own physical stock.quant — physical stock wins).

    Mirrors buz_stock_current_report's bom_available_by_location logic
    (models/stock_current_report.py): a kit is available at a location only
    if every one of its BOM components has free stock there, and the
    buildable qty is the minimum (component free qty // required qty) across
    all components.
    """
    env.cr.execute("""
        WITH kit_requirement AS (
            SELECT pp.id AS kit_product_id,
                   bl.product_id AS component_id,
                   SUM(bl.product_qty) AS component_qty
            FROM mrp_bom bom
            JOIN product_product pp ON pp.product_tmpl_id = bom.product_tmpl_id
                AND (bom.product_id IS NULL OR bom.product_id = pp.id)
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN mrp_bom_line bl ON bl.bom_id = bom.id
            WHERE bom.active = true
              AND bom.type IN ('normal', 'phantom')
              AND pp.active = true AND pt.active = true
              AND NOT (pp.id = ANY(%(excluded_ids)s))
            GROUP BY pp.id, bl.product_id
        ),
        kit_requirement_size AS (
            SELECT kit_product_id, COUNT(*) AS n_lines
            FROM kit_requirement
            GROUP BY kit_product_id
        ),
        component_stock AS (
            SELECT product_id,
                   GREATEST(COALESCE(SUM(quantity), 0) - COALESCE(SUM(reserved_quantity), 0), 0) AS qty
            FROM stock_quant
            WHERE location_id = %(location_id)s
            GROUP BY product_id
        )
        SELECT kr.kit_product_id AS product_id,
               MIN(FLOOR(cs.qty / NULLIF(kr.component_qty, 0))) AS bom_qty
        FROM kit_requirement kr
        JOIN kit_requirement_size krs ON krs.kit_product_id = kr.kit_product_id
        JOIN component_stock cs ON cs.product_id = kr.component_id AND cs.qty > 0
        GROUP BY kr.kit_product_id, krs.n_lines
        HAVING COUNT(*) = krs.n_lines
           AND MIN(FLOOR(cs.qty / NULLIF(kr.component_qty, 0))) > 0
    """, {'location_id': location_id, 'excluded_ids': exclude_product_ids})
    return {row['product_id']: float(row['bom_qty']) for row in env.cr.dictfetchall()}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    can_be_pos = fields.Boolean(string='Can be POS', default=False)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    can_be_pos = fields.Boolean(
        string='Can be POS',
        related='product_tmpl_id.can_be_pos',
        readonly=False
    )

    @api.model
    def _pos_lite_kit_stock_map(self, location_id, exclude_product_ids):
        """Return {product_id: buildable_qty} for BOM-kit products buildable
        at location_id, excluding products already covered by their own
        stock.quant (see _kit_stock_map above)."""
        return _kit_stock_map(self.env, location_id, exclude_product_ids)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not self.env.context.get('pos_lite_search'):
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        args = list(args or [])
        name = (name or '').strip()
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        domain = [
            '|', '|', '|', '|',
            ('default_code', '=', name),
            ('barcode', '=', name),
            ('default_code', operator, name),
            ('barcode', operator, name),
            ('name', operator, name),
        ]
        products = self.search(domain + args, limit=limit)
        if products:
            return [(p.id, p.display_name) for p in products]
        return super().name_search(name=name, args=args, operator=operator, limit=limit)
