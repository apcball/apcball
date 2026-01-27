Goal: Add location_id to stock.valuation.layer (SVL), compute/store consistently, give a safe/fast recompute via ORM and an optional ultra-fast SQL path for very large DBs. Include server action, optional cron, and views.

Project
	•	Addon name: stock_valuation_location
	•	Odoo: 17 Community
	•	Depends: stock_account
	•	License: LGPL-3
	•	Company: MOGEN (buz)

⸻

Deliverables (files & content)

1) __manifest__.py
	•	Fix syntax.
	•	Update meta (author/website).
	•	Data files include: groups, views, server action, optional cron.

    {
    "name": "buz Stock Valuation Location",
    "version": "17.0.1.0.0",
    "summary": "Add Location Information to Stock Valuation",
    "category": "Inventory/Accounting",
    "author": "MOGEN (buz)",
    "website": "https://mogdev.work",
    "license": "LGPL-3",
    "depends": ["stock_account"],
    "data": [
        "security/stock_valuation_location_groups.xml",
        "views/stock_valuation_layer_views.xml",
        "data/stock_valuation_recompute_action.xml",
        "data/ir_cron_recompute_location.xml",    # optional cron (create but can be inactive by default)
    ],
    "assets": {},
    "installable": True,
    "auto_install": False,
}

2) models/stock_valuation_layer.py
	•	Add computed, stored, indexed location_id.
	•	Proper @api.depends(...).
	•	Action to ORM-recompute.
	•	Fast SQL path (optional), with safety: advisory lock, single-transaction, optional limit, and a dry-run that only returns affected count.
    from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        compute="_compute_location_id",
        store=True,
        compute_sudo=True,
        index=True,
        help="Internal location chosen from the move (source if internal, else destination if internal). "
             "Remains empty for SVLs without stock_move_id (e.g., some Landed Costs).",
    )

    @api.depends(
        "stock_move_id",
        "stock_move_id.location_id.usage",
        "stock_move_id.location_dest_id.usage",
    )
    def _compute_location_id(self):
        for svl in self:
            move = svl.stock_move_id
            if not move:
                svl.location_id = False
                continue
            if move.location_id.usage == "internal":
                svl.location_id = move.location_id
            elif move.location_dest_id.usage == "internal":
                svl.location_id = move.location_dest_id
            else:
                svl.location_id = False

    def action_recompute_stock_valuation_location(self):
        """Safe ORM recompute (batch-aware, no manual commits)."""
        svls = self.env["stock.valuation.layer"].search([("stock_move_id", "!=", False)])
        # ORM-managed batched recompute of stored compute fields
        svls.recompute()
        return {"type": "ir.actions.client", "tag": "reload"}

    # -------------------------
    # Ultra-fast SQL path (optional)
    # -------------------------
    def _sql_fast_fill_location(self, dry_run=False, limit=None, lock_key=827174):
        """
        Maintenance-usage only. Re-sync location_id using single SQL UPDATE.
        - dry_run=True: return number of would-be affected rows (no update).
        - limit: cap number of updates (for incremental runs).
        - Uses advisory lock to prevent concurrent runs.

        Returns: dict(count=int, dry_run=bool, limited=bool)
        """
        if self.env.context.get("svl_sql_fast_disallow"):
            raise UserError(_("SQL fast path is disallowed by context."))

        cr = self.env.cr
        # Take advisory lock
        cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (int(lock_key),))
        locked = cr.fetchone()[0]
        if not locked:
            raise UserError(_("Another recompute is running (advisory lock busy). Try again later."))

        limit_clause = "" if not limit else f" LIMIT {int(limit)}"

        # Build a CTE to compute new location from both ends of the move
        cte = """
            WITH target AS (
                SELECT
                    svl.id           AS svl_id,
                    CASE
                        WHEN sl.usage = 'internal'  THEN sl.id
                        WHEN sld.usage = 'internal' THEN sld.id
                        ELSE NULL
                    END AS new_loc
                FROM stock_valuation_layer svl
                JOIN stock_move sm   ON sm.id  = svl.stock_move_id
                JOIN stock_location sl  ON sl.id  = sm.location_id
                JOIN stock_location sld ON sld.id = sm.location_dest_id
                WHERE svl.stock_move_id IS NOT NULL
            ),
            diff AS (
                SELECT svl_id, new_loc
                FROM target
                JOIN stock_valuation_layer svl ON svl.id = target.svl_id
                WHERE (svl.location_id IS DISTINCT FROM target.new_loc)
            )
        """

        if dry_run:
            cr.execute(cte + " SELECT COUNT(*) FROM diff;")
            count = cr.fetchone()[0]
            return {"count": count, "dry_run": True, "limited": False}

        # UPDATE with optional LIMIT via primary key
        # (PostgreSQL doesn't allow LIMIT directly on UPDATE; we choose a safe subset)
        sql = cte + f"""
            UPDATE stock_valuation_layer svl
               SET location_id = diff.new_loc
              FROM (
                  SELECT svl_id, new_loc
                  FROM diff
                  ORDER BY svl_id
                  {limit_clause}
              ) AS diff
             WHERE svl.id = diff.svl_id
             RETURNING svl.id;
        """
        cr.execute(sql)
        updated_rows = cr.fetchall()
        return {"count": len(updated_rows), "dry_run": False, "limited": bool(limit)}
        Notes
	•	ใช้ advisory lock กันยิงซ้อน
	•	dry_run ให้เช็คผลก่อนลงมือจริง
	•	limit ช่วย rollout ทีละก้อนใน DB ใหญ่
	•	ไม่ใส่ commit()—ปล่อยให้ Odoo/transaction manager จัดการ

⸻

3) wizards/stock_valuation_location_fast_sql_wizard.py (เล็กๆ เพื่อ UX)
	•	Wizard ให้ระบุ dry_run, limit, lock_key.
	•	เรียก _sql_fast_fill_location().
	•	แสดงจำนวนแถวที่จะ/ที่ถูกอัปเดต.
    from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockValuationLocationFastSQLWizard(models.TransientModel):
    _name = "stock.valuation.location.fast.sql.wizard"
    _description = "Fast SQL Recompute (SVL.location_id)"

    dry_run = fields.Boolean(default=True, help="If enabled, does not update. Only show affected count.")
    limit = fields.Integer(default=0, help="0 means no limit. Use for incremental updates.")
    lock_key = fields.Integer(default=827174, help="Advisory lock key to avoid concurrent runs.")

    result_msg = fields.Text(readonly=True)

    def action_run(self):
        limit = self.limit or None
        res = self.env["stock.valuation.layer"].with_context()._sql_fast_fill_location(
            dry_run=self.dry_run, limit=limit, lock_key=self.lock_key
        )
        msg = _(
            "Fast SQL path executed.\nDry run: %(dry)s\nLimited: %(lim)s\nAffected rows: %(cnt)s",
            dry="Yes" if res["dry_run"] else "No",
            lim="Yes" if res["limited"] else "No",
            cnt=res["count"],
        )
        self.write({"result_msg": msg})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "name": _("SVL Location — Fast SQL Result"),
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
        4) views/stock_valuation_layer_views.xml
	•	Add location_id in SVL tree/form + search filter/group_by.
    <odoo>
  <record id="view_stock_valuation_layer_tree_inherit_loc" model="ir.ui.view">
    <field name="name">stock.valuation.layer.tree.location</field>
    <field name="model">stock.valuation.layer</field>
    <field name="inherit_id" ref="stock_account.view_stock_valuation_layer_tree"/>
    <field name="arch" type="xml">
      <xpath expr="//tree/field[@name='product_id']" position="after">
        <field name="location_id"/>
      </xpath>
    </field>
  </record>

  <record id="view_stock_valuation_layer_search_inherit_loc" model="ir.ui.view">
    <field name="name">stock.valuation.layer.search.location</field>
    <field name="model">stock.valuation.layer</field>
    <field name="inherit_id" ref="stock_account.view_stock_valuation_layer_search"/>
    <field name="arch" type="xml">
      <xpath expr="//search" position="inside">
        <field name="location_id" filter_domain="[('location_id','=',self)]" string="Location"/>
        <filter string="Group By Location" context="{'group_by':'location_id'}"/>
      </xpath>
    </field>
  </record>

  <!-- Wizard action & menu (optional) -->
  <record id="action_fast_sql_wizard" model="ir.actions.act_window">
    <field name="name">SVL Location — Fast SQL</field>
    <field name="res_model">stock.valuation.location.fast.sql.wizard</field>
    <field name="view_mode">form</field>
    <field name="target">new</field>
  </record>

  <menuitem id="menu_inventory_valuation_fast_sql"
            name="SVL Location — Fast SQL"
            parent="stock.menu_stock_inventory_control"
            action="action_fast_sql_wizard"
            groups="stock_valuation_location.group_svl_location_admin"/>
</odoo>
5) security/stock_valuation_location_groups.xml
	•	Minimal admin group to access fast SQL wizard.
    (ไม่มีโมเดลใหม่ จึงไม่ต้องมี ir.model.access เพิ่ม)

⸻

6) data/stock_valuation_recompute_action.xml
	•	Server action (ORM recompute path) + menuitem (optional).

    <odoo>
  <record id="ir_actions_server_recompute_location" model="ir.actions.server">
    <field name="name">Recompute SVL Location (ORM)</field>
    <field name="model_id" ref="stock_account.model_stock_valuation_layer"/>
    <field name="state">code</field>
    <field name="code">
      action = env["stock.valuation.layer"].action_recompute_stock_valuation_location()
    </field>
  </record>

  <menuitem id="menu_inventory_valuation_recompute_location"
            name="Recompute SVL Location (ORM)"
            parent="stock.menu_stock_inventory_control"
            action="ir_actions_server_recompute_location"/>
</odoo>

7) data/ir_cron_recompute_location.xml (optional; inactive by default)
	•	Cron that calls ORM recompute (safer). Keep it disabled initially.
    <odoo>
  <record id="ir_cron_svl_location_recompute" model="ir.cron">
    <field name="name">SVL Location ORM Recompute</field>
    <field name="active">False</field>
    <field name="model_id" ref="stock_account.model_stock_valuation_layer"/>
    <field name="state">code</field>
    <field name="code">model.action_recompute_stock_valuation_location()</field>
    <field name="interval_number">24</field>
    <field name="interval_type">hours</field>
    <field name="numbercall">-1</field>
  </record>
</odoo>
8) wizards/__init__.py
from . import stock_valuation_location_fast_sql_wizard
9) models/__init__.py
from . import stock_valuation_layer
Functional rules
	1.	Computation rule

	•	If stock_move_id.location_id.usage == 'internal' → use that.
	•	Else if stock_move_id.location_dest_id.usage == 'internal' → use that.
	•	Else → False (e.g., moves between external/supplier/customer with no internal side).
	•	SVL without move (e.g., some Landed Costs) → False.

	2.	Recompute options

	•	ORM path (default & safe): action_recompute_stock_valuation_location()
	•	Fast SQL path (admin-only) via wizard:
	•	dry_run to preview affected rows.
	•	limit for chunked rollout.
	•	Advisory lock prevents concurrent runs.

	3.	Views

	•	location_id appears in SVL list/form, searchable, groupable.

⸻

Post-Install checklist
	•	Upgrade: -u stock_valuation_location
	•	Open SVL list → verify new Location column.
	•	Run ORM Recompute once (server action).
	•	For very large DB:
	1.	Open SVL Location — Fast SQL wizard.
	2.	Run Dry-run → check affected count.
	3.	Run with limit (e.g., 100k) until count → 0.

⸻

QA / Acceptance
	•	Create internal transfer → SVL shows location_id (source if internal else dest).
	•	Customer delivery (internal → customer) → location = internal source.
	•	Vendor receipt (supplier → internal) → location = internal dest.
	•	Landed Cost SVLs keep location_id = False.
	•	Recompute paths idempotent: repeated runs don’t change data once correct.

⸻

Nice-to-have (optional, only if time permits)
	•	Migration hook to trigger ORM recompute once on install/upgrade.
	•	Pivot preset: Inventory Valuation by location_id.

⸻

Implement exactly as specified above. Use clean, production-grade code, docstrings, and helpful help-texts.