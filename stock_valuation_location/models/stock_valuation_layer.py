import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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

    @api.depends("stock_move_id")
    def _compute_location_id(self):
        """Compute location_id with memory-efficient batch processing."""
        # Clear all first
        for svl in self:
            svl.location_id = False
        
        # Filter out records without moves
        svls_with_moves = self.filtered(lambda s: s.stock_move_id)
        if not svls_with_moves:
            return
        
        # Batch read to avoid N+1 queries
        move_data = svls_with_moves.mapped('stock_move_id').read([
            'location_id', 'location_dest_id'
        ])
        move_dict = {m['id']: m for m in move_data}
        
        # Collect all location IDs to fetch usage in batch
        location_ids = set()
        for move in move_data:
            if move['location_id']:
                location_ids.add(move['location_id'][0])
            if move['location_dest_id']:
                location_ids.add(move['location_dest_id'][0])
        
        # Batch read location usage
        if location_ids:
            locations = self.env['stock.location'].browse(list(location_ids)).read(['usage'])
            location_usage = {loc['id']: loc['usage'] for loc in locations}
        else:
            location_usage = {}
        
        # Process each SVL with cached data
        for svl in svls_with_moves:
            move = move_dict.get(svl.stock_move_id.id)
            if not move:
                continue
            
            # Check source location
            if move['location_id']:
                loc_id = move['location_id'][0]
                if location_usage.get(loc_id) == 'internal':
                    svl.location_id = loc_id
                    continue
            
            # Check destination location
            if move['location_dest_id']:
                loc_id = move['location_dest_id'][0]
                if location_usage.get(loc_id) == 'internal':
                    svl.location_id = loc_id

    def action_recompute_stock_valuation_location(self, batch_size=1000):
        """Safe ORM recompute with batching to prevent memory/timeout issues."""
        _logger = logging.getLogger(__name__)
        
        # Count total records to process
        total_count = self.env["stock.valuation.layer"].search_count([
            ("stock_move_id", "!=", False)
        ])
        
        if total_count == 0:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Records"),
                    "message": _("No stock valuation layers with moves found."),
                    "type": "info",
                }
            }
        
        _logger.info(f"Starting SVL location recompute for {total_count} records in batches of {batch_size}")
        
        # Process in batches to avoid memory issues
        processed = 0
        offset = 0
        
        while offset < total_count:
            # Search with limit and offset
            batch = self.env["stock.valuation.layer"].search([
                ("stock_move_id", "!=", False)
            ], limit=batch_size, offset=offset)
            
            if not batch:
                break
            
            # Process this batch
            batch._compute_location_id()
            
            processed += len(batch)
            offset += batch_size
            
            # Commit every batch to avoid transaction timeout
            self.env.cr.commit()
            
            _logger.info(f"Processed {processed}/{total_count} SVL records")
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Recompute Complete"),
                "message": _("Successfully recomputed location for %s stock valuation layers.") % processed,
                "type": "success",
                "sticky": False,
            }
        }

    # -------------------------
    # Ultra-fast SQL path (optional)
    # -------------------------
    def _sql_fast_fill_location(self, dry_run=False, limit=None, lock_key=827174, timeout=300):
        """
        Maintenance-usage only. Re-sync location_id using single SQL UPDATE.
        - dry_run=True: return number of would-be affected rows (no update).
        - limit: cap number of updates (for incremental runs).
        - timeout: query timeout in seconds (default 300s = 5 minutes).
        - Uses advisory lock to prevent concurrent runs.

        Returns: dict(count=int, dry_run=bool, limited=bool)
        """
        if self.env.context.get("svl_sql_fast_disallow"):
            raise UserError(_("SQL fast path is disallowed by context."))

        cr = self.env.cr
        
        # Set statement timeout to prevent indefinite hangs
        cr.execute(f"SET LOCAL statement_timeout = '{int(timeout * 1000)}';")  # milliseconds
        
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
            _logger.info(f"SVL location dry-run: {count} records would be affected")
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
        
        _logger.info(f"Executing SVL location SQL update (limit={limit or 'none'})")
        cr.execute(sql)
        updated_rows = cr.fetchall()
        count = len(updated_rows)
        _logger.info(f"SVL location SQL update completed: {count} records updated")
        
        return {"count": count, "dry_run": False, "limited": bool(limit)}
