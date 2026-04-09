from odoo import models, fields, api, _, exceptions
import logging
from datetime import datetime, time, date as date_type
import pytz

_logger = logging.getLogger(__name__)

class FifoResetService(models.AbstractModel):
    _name = 'fifo.reset.service'
    _description = 'FIFO Reset Core Service'

    @api.model
    def run(self, dry_run=False, company_id=False, reset_date=False, warehouse_ids=False):
        if not company_id:
            company_id = self.env.company.id
        if not reset_date:
            reset_date = fields.Date.today()
            
        env_company = self.env['res.company'].browse(company_id)
        # Add skip_warehouse_consistency_check to bypass validation during reset
        service = self.with_company(env_company).with_context(skip_warehouse_consistency_check=True)
        
        # แปลง reset_date เป็น datetime end-of-day สำหรับ filter Datetime fields
        naive_dt = False
        if isinstance(reset_date, date_type) and not isinstance(reset_date, datetime):
            naive_dt = datetime.combine(reset_date, time.max)  # 23:59:59.999999
        elif isinstance(reset_date, str):
            naive_dt = datetime.strptime(reset_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            
        reset_dt = False
        if naive_dt:
            # ปรับ Timezone ย้อนกลับให้เป็น UTC อิงจากเวลาของ User เพื่อป้องกันวันที่เหลื่อมไปอีกวัน (เช่น +7 ทำให้ 23:59 กลายเป็น 06:59 ของวันถัดไป)
            tz_name = self.env.user.tz or self.env.context.get('tz')
            if not tz_name or tz_name == 'UTC':
                tz_name = 'Asia/Bangkok'  # Default to Thailand timezone if user tz is missing
            user_tz = pytz.timezone(tz_name)
            local_dt = user_tz.localize(naive_dt)
            utc_dt = local_dt.astimezone(pytz.utc)
            reset_dt = utc_dt.replace(tzinfo=None)
        
        # Resolve warehouses
        Warehouse = self.env['stock.warehouse']
        if warehouse_ids:
            warehouses = Warehouse.browse(warehouse_ids).filtered(
                lambda w: w.company_id.id == company_id
            )
        else:
            warehouses = Warehouse.search([('company_id', '=', company_id)])
        
        if not warehouses:
            raise exceptions.UserError(_("No warehouses found for the selected company."))

        summary = {
            'total_products': 0,
            'total_quants': 0,
            'before_value': 0.0,
            'after_value': 0.0,
            'error_message': False,
            'warehouse_details': [],  # per-warehouse progress
        }
        status = 'success'

        # Bug #6 fix: ใช้ ALL SVLs เพราะ module ล้างทั้งหมดอยู่แล้ว
        svls_before = service.env['stock.valuation.layer'].search([
            ('company_id', '=', company_id),
        ])
        summary['before_value'] = sum(svls_before.mapped('value'))

        try:
            if dry_run:
                with service.env.cr.savepoint():
                    service._execute_reset_pipeline(
                        summary, warehouses=warehouses, reset_dt=reset_dt, dry_run=True
                    )
                    svls_after = service.env['stock.valuation.layer'].search([
                        ('company_id', '=', company_id),
                    ])
                    summary['after_value'] = sum(svls_after.mapped('value'))
                    raise Exception("__DRY_RUN__")
            else:
                service._execute_reset_pipeline(
                    summary, warehouses=warehouses, reset_dt=reset_dt, dry_run=False
                )
                svls_after = service.env['stock.valuation.layer'].search([
                    ('company_id', '=', company_id),
                ])
                summary['after_value'] = sum(svls_after.mapped('value'))

        except Exception as e:
            if str(e) == "__DRY_RUN__":
                pass
            else:
                status = 'error'
                summary['error_message'] = str(e)
                _logger.exception("FIFO Reset Error")
                
        # Logging
        if not dry_run or status == 'error':
            # Build progress detail text
            progress_lines = []
            for wd in summary.get('warehouse_details', []):
                progress_lines.append(
                    "✅ %s — %d quants, %d products" % (
                        wd['name'], wd['quants'], wd['products']
                    ) if wd['status'] == 'success' else
                    "❌ %s — ERROR: %s" % (wd['name'], wd.get('error', ''))
                )
            progress_detail = "\n".join(progress_lines) or "No warehouse details"

            self.env['fifo.reset.log'].sudo().create({
                'company_id': company_id,
                'reset_date': reset_date,
                'total_products': summary['total_products'],
                'total_quants': summary['total_quants'],
                'before_value': summary['before_value'],
                'after_value': summary['after_value'],
                'status': status,
                'error_message': summary['error_message'] or "",
                'is_dry_run': dry_run,
                'warehouse_ids': [(6, 0, warehouses.ids)],
                'progress_detail': progress_detail,
            })
            
        return {
            'status': status,
            'summary': summary
        }

    def _execute_reset_pipeline(self, summary, warehouses=None, reset_dt=False, dry_run=False):
        """Execute the reset pipeline PER WAREHOUSE.
        
        Flow:
        1. Loop per warehouse: safety check → clear reservations → cancel pickings → reset quants
           - commit after each warehouse (actual run only)
        2. After all warehouses: flush SVL + JE (once) → validate
        
        NOTE: dry_run = True → ไม่ commit per-warehouse (ใช้ savepoint rollback ทั้งหมด)
        """
        if not warehouses:
            raise exceptions.UserError(_("No warehouses to process."))

        # Global safety check (accounting lock date etc.)
        self._check_safety_global(reset_dt=reset_dt)

        for wh in warehouses:
            wh_detail = {
                'id': wh.id,
                'name': wh.name,
                'quants': 0,
                'products': 0,
                'status': 'pending',
            }
            try:
                _logger.info("=" * 60)
                _logger.info("FIFO Reset: START processing warehouse [%s] %s", wh.code, wh.name)
                _logger.info("=" * 60)

                # Get all internal locations for this warehouse
                locations = self.env['stock.location'].search([
                    ('warehouse_id', '=', wh.id),
                    ('usage', '=', 'internal'),
                    ('company_id', '=', self.env.company.id),
                ])
                if not locations:
                    _logger.info("FIFO Reset: Warehouse %s has no internal locations, skipping.", wh.name)
                    wh_detail['status'] = 'success'
                    summary['warehouse_details'].append(wh_detail)
                    continue

                # Step 1: Check safety per warehouse
                self._check_safety_warehouse(locations, reset_dt=reset_dt)

                # Step 2: Clear reservations for this warehouse
                self._clear_reservations(locations, reset_dt=reset_dt)

                # Step 3: Cancel pickings for this warehouse
                self._cancel_pickings(locations, reset_dt=reset_dt)

                # Step 4: Reset quants for this warehouse
                wh_quants, wh_products = self._reset_quants(locations, warehouse=wh, reset_dt=reset_dt, dry_run=dry_run)
                wh_detail['quants'] = wh_quants
                wh_detail['products'] = wh_products
                summary['total_quants'] += wh_quants
                summary['total_products'] += wh_products

                wh_detail['status'] = 'success'
                _logger.info(
                    "FIFO Reset: DONE warehouse [%s] %s — %d quants, %d products",
                    wh.code, wh.name, wh_quants, wh_products,
                )

                # Commit per warehouse (actual run only — dry run uses savepoint rollback)
                if not dry_run:
                    self.env.cr.commit()
                    _logger.info("FIFO Reset: Committed warehouse [%s] %s", wh.code, wh.name)

            except Exception as e:
                wh_detail['status'] = 'error'
                wh_detail['error'] = str(e)
                _logger.exception(
                    "FIFO Reset: ERROR processing warehouse [%s] %s: %s",
                    wh.code, wh.name, str(e),
                )
                # Re-raise to stop pipeline (ไม่ข้าม warehouse ที่ error)
                summary['warehouse_details'].append(wh_detail)
                raise

            summary['warehouse_details'].append(wh_detail)

        # After all warehouses: Flush SVL + JE (ทำครั้งเดียว)
        _logger.info("=" * 60)
        _logger.info("FIFO Reset: Flushing ALL SVL and creating Journal Entries")
        _logger.info("=" * 60)
        self._flush_svl(summary, warehouses=warehouses, reset_dt=reset_dt)

        if not dry_run:
            self.env.cr.commit()
            _logger.info("FIFO Reset: Committed SVL flush")

        # Final validation
        self._validate_fifo(warehouses=warehouses)

    # ─── Safety Checks ────────────────────────────────────────────

    def _check_safety_global(self, reset_dt=False):
        """Global safety: accounting lock date check."""
        company = self.env.company

        if reset_dt:
            reset_d = reset_dt.date() if isinstance(reset_dt, datetime) else reset_dt
            if company.period_lock_date and reset_d <= company.period_lock_date:
                raise exceptions.UserError(_(
                    "Cannot reset to %s: Accounting period is locked until %s. "
                    "Please unlock the period first (Settings > Accounting > Lock Dates)."
                ) % (reset_d, company.period_lock_date))
            if company.fiscalyear_lock_date and reset_d <= company.fiscalyear_lock_date:
                raise exceptions.UserError(_(
                    "Cannot reset to %s: Fiscal year is locked until %s. "
                    "Please unlock the fiscal year first (Settings > Accounting > Lock Dates)."
                ) % (reset_d, company.fiscalyear_lock_date))

    def _check_safety_warehouse(self, locations, reset_dt=False):
        """Per-warehouse safety: check for unknown picking states."""
        company_id = self.env.company.id
        standard_states = ['done', 'cancel', 'waiting', 'confirmed', 'assigned', 'draft']

        # Check for unknown/custom states in this warehouse
        domain_unknown = [
            ('company_id', '=', company_id),
            ('state', 'not in', standard_states),
            '|',
            ('location_id', 'in', locations.ids),
            ('location_dest_id', 'in', locations.ids),
        ]
        if reset_dt:
            domain_unknown += [('scheduled_date', '<=', reset_dt)]
        invalid_pickings = self.env['stock.picking'].search_count(domain_unknown)
        if invalid_pickings > 0:
            raise exceptions.UserError(_(
                "Cannot proceed: Found %s transfers in an unknown/custom state "
                "for warehouse locations. Please resolve them manually before running the reset."
            ) % invalid_pickings)

        # Warn about open pickings
        domain_open = [
            ('company_id', '=', company_id),
            ('state', 'not in', ['done', 'cancel']),
            '|',
            ('location_id', 'in', locations.ids),
            ('location_dest_id', 'in', locations.ids),
        ]
        if reset_dt:
            domain_open += [('scheduled_date', '<=', reset_dt)]
        open_count = self.env['stock.picking'].search_count(domain_open)
        if open_count > 0:
            _logger.warning(
                "FIFO Reset: %s open pickings will be force-cancelled for these locations.",
                open_count
            )

    # ─── Per-Warehouse Steps ──────────────────────────────────────

    def _clear_reservations(self, locations, reset_dt=False):
        """Step 1: Clear reservations for moves involving this warehouse's locations."""
        domain = [
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ['assigned', 'partially_available']),
            '|',
            ('location_id', 'in', locations.ids),
            ('location_dest_id', 'in', locations.ids),
        ]
        if reset_dt:
            domain += [('date', '<=', reset_dt)]
        moves = self.env['stock.move'].search(domain)
        if moves:
            _logger.info("FIFO Reset: Unreserving %d moves", len(moves))
            moves._do_unreserve()

    def _cancel_pickings(self, locations, reset_dt=False):
        """Step 2: Cancel open pickings for this warehouse's locations."""
        domain = [
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ['waiting', 'confirmed', 'assigned', 'draft']),
            '|',
            ('location_id', 'in', locations.ids),
            ('location_dest_id', 'in', locations.ids),
        ]
        if reset_dt:
            domain += [('scheduled_date', '<=', reset_dt)]
        pickings = self.env['stock.picking'].search(domain)
        if pickings:
            _logger.info("FIFO Reset: Cancelling %d pickings", len(pickings))
            pickings.action_cancel()

    def _reset_quants(self, locations, warehouse, reset_dt=False, dry_run=False):
        """Step 3: Reset quants for this warehouse's locations.
        
        Returns:
            tuple: (quant_count, product_count)
        """
        Quant = self.env['stock.quant']

        # No need to search all products first. Just search quants directly.
        # But Odoo only values storable products, standard filter is `product_id.type = 'product'`
        quants = Quant.search([
            ('product_id.type', '=', 'product'),
            ('location_id', 'in', locations.ids),
            ('company_id', '=', self.env.company.id),
        ])

        quants_to_reset = quants.filtered(lambda q: q.quantity != 0)

        if not quants_to_reset:
            return 0, 0

        quant_count = len(quants_to_reset)
        product_count = len(quants_to_reset.mapped('product_id'))
        
        CHUNK_SIZE = 500
        quant_ids = quants_to_reset.ids
        total_chunks = (quant_count + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        _logger.info("FIFO Reset: Processing %d quants in %d chunks (Max %d per chunk)", quant_count, total_chunks, CHUNK_SIZE)

        Move = self.env['stock.move']
        
        for i in range(0, quant_count, CHUNK_SIZE):
            chunk_ids = quant_ids[i:i + CHUNK_SIZE]
            chunk_quants = Quant.browse(chunk_ids)
            
            for quant in chunk_quants:
                quant.write({'inventory_quantity': 0})

            # Force วันที่ inventory adjustment = reset_date และบังคับผูก warehouse
            ctx = {'fifo_warehouse_id': warehouse.id}
            if reset_dt:
                ctx.update({
                    'inventory_date': reset_dt.date(),
                    'force_period_date': reset_dt.date(),
                })
            quant_env = chunk_quants.with_context(**ctx)

            # จับ last move ID และ last SVL ID ก่อน _apply_inventory เพื่อหา records ที่สร้างใหม่
            last_move_id = Move.search(
                [('company_id', '=', self.env.company.id)],
                order='id desc', limit=1,
            ).id or 0
            
            last_svl_id = self.env['stock.valuation.layer'].search(
                [('company_id', '=', self.env.company.id)],
                order='id desc', limit=1,
            ).id or 0

            try:
                quant_env._apply_inventory()
                
                # หลังทำเสร็จ บังคับยัด warehouse_id ทันที
                # Fix: ครอบคลุม 2 กรณี:
                #  1) SVL ที่ผูกกับ new moves (ปกติ)
                #  2) SVL ที่สร้างใหม่หลัง last_svl_id แต่ไม่ผูก move (จาก FIFO cascade, rounding layers, etc.)
                new_moves = Move.search([
                    ('company_id', '=', self.env.company.id),
                    ('id', '>', last_move_id),
                ])
                if new_moves:
                    self.env.cr.execute(
                        "UPDATE stock_valuation_layer SET warehouse_id = %s WHERE stock_move_id IN %s AND warehouse_id IS NULL",
                        (warehouse.id, tuple(new_moves.ids))
                    )
                # Fix orphan layers: layers created after last_svl_id but not linked to new moves
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET warehouse_id = %s "
                    "WHERE id > %s AND warehouse_id IS NULL AND company_id = %s",
                    (warehouse.id, last_svl_id, self.env.company.id)
                )
            except Exception as e:
                raise

            # Odoo _action_done() forces date=now() — ต้อง overwrite เป็น reset_dt
            if reset_dt:
                new_moves = Move.search([
                    ('company_id', '=', self.env.company.id),
                    ('id', '>', last_move_id),
                ])
                if new_moves:
                    # 1) Fix stock.move.date → SVL.date (related field)
                    new_moves.write({'date': reset_dt})

                    # 2) Override stock.move.line.date
                    sml = self.env['stock.move.line'].search([
                        ('move_id', 'in', new_moves.ids),
                    ])
                    if sml:
                        sml.write({'date': reset_dt})

                    # 3) Override SVL create_date
                    inv_svls = self.env['stock.valuation.layer'].search([
                        ('stock_move_id', 'in', new_moves.ids),
                    ])
                    if inv_svls:
                        self.env.cr.execute(
                            "UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s",
                            (reset_dt, tuple(inv_svls.ids)),
                        )

                    # 4) Fix related account.move dates
                    for move in new_moves:
                        for am in move.account_move_ids:
                            if am.date != reset_dt.date():
                                try:
                                    if am.state == 'posted':
                                        am.button_draft()
                                    am.write({'date': reset_dt.date()})
                                    am.action_post()
                                except Exception as e:
                                    _logger.warning(
                                        "FIFO Reset: Could not re-date account.move %s: %s",
                                        am.id, str(e),
                                    )
            
            if not dry_run:
                self.env.cr.commit()
            
            # Clear ORM cache context for the environment to free MEMORY!
            self.env.invalidate_all()
            _logger.info("FIFO Reset: Finished chunk %d of %d", (i // CHUNK_SIZE) + 1, total_chunks)

        return quant_count, product_count

    # ─── SVL Flush (Global — after all warehouses) ────────────────

    def _flush_svl(self, summary, warehouses=None, reset_dt=False):
        """Flush residual SVL + create accounting JE per warehouse.
        """
        if not warehouses:
            warehouses = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)])
            
        # ล้าง SVL ของคลังที่ระบุ รวมถึง ghost layers (warehouse_id = False) ด้วย
        domain = [
            ('company_id', '=', self.env.company.id),
            '|',
            ('warehouse_id', 'in', warehouses.ids),
            ('warehouse_id', '=', False)
        ]
        
        svls = self.env['stock.valuation.layer'].search(domain)
        if not svls:
            return

        default_wh_id = warehouses[0].id if warehouses else False

        if default_wh_id:
            # 🔴 Fix Ghost Layers: Before we group and flush, bind ghost layers
            # to the CORRECT warehouse. Try to determine warehouse from the stock_move's
            # internal locations first, otherwise fall back to processing warehouse.
            
            # Step 1: Fix ghost layers that have a linked stock_move with identifiable warehouse
            self.env.cr.execute("""
                UPDATE stock_valuation_layer svl
                SET warehouse_id = COALESCE(
                    -- Try source location's warehouse (for outgoing/decrease moves)
                    (SELECT sl.warehouse_id FROM stock_move sm
                     JOIN stock_location sl ON sl.id = sm.location_id
                     WHERE sm.id = svl.stock_move_id AND sl.usage = 'internal' AND sl.warehouse_id IS NOT NULL
                     LIMIT 1),
                    -- Try dest location's warehouse (for incoming/increase moves) 
                    (SELECT sl.warehouse_id FROM stock_move sm
                     JOIN stock_location sl ON sl.id = sm.location_dest_id
                     WHERE sm.id = svl.stock_move_id AND sl.usage = 'internal' AND sl.warehouse_id IS NOT NULL
                     LIMIT 1)
                )
                WHERE svl.warehouse_id IS NULL 
                AND svl.company_id = %s
                AND svl.stock_move_id IS NOT NULL
                AND EXISTS (
                    SELECT 1 FROM stock_move sm
                    JOIN stock_location sl ON sl.id IN (sm.location_id, sm.location_dest_id)
                    WHERE sm.id = svl.stock_move_id AND sl.usage = 'internal' AND sl.warehouse_id IS NOT NULL
                )
            """, (self.env.company.id,))
            
            # Step 2: Remaining ghost layers (no stock_move or can't determine) → default warehouse
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET warehouse_id = %s "
                "WHERE warehouse_id IS NULL AND company_id = %s",
                (default_wh_id, self.env.company.id)
            )
            # Invalidate cache so read_group sees the updated warehouse_ids
            self.env['stock.valuation.layer'].invalidate_model(['warehouse_id'])

        # Use read_group to group all residuals by product and warehouse in DB level
        groups = self.env['stock.valuation.layer'].read_group(
            domain,
            ['product_id', 'warehouse_id', 'quantity:sum', 'value:sum'],
            ['product_id', 'warehouse_id'],
            lazy=False
        )

        # Aggregate the groups by (product_id, target_warehouse_id)
        # This solves the Ghost SVL issue because ghost layers (warehouse_id=False) 
        # and previously balanced layers (warehouse_id=target) will sum out to 0.
        aggregated_data = {}
        for group in groups:
            prod_id = group.get('product_id')[0] if group.get('product_id') else False
            if not prod_id:
                continue

            wh_id = group.get('warehouse_id')[0] if group.get('warehouse_id') else False
            qty = group.get('quantity', 0.0)
            val = group.get('value', 0.0)

            target_wh_id = wh_id if wh_id is not False else default_wh_id

            key = (prod_id, target_wh_id)
            if key not in aggregated_data:
                aggregated_data[key] = {'qty': 0.0, 'val': 0.0}

            aggregated_data[key]['qty'] += qty
            aggregated_data[key]['val'] += val

        flushed_count = 0
        for (prod_id, target_wh_id), data in aggregated_data.items():
            qty = data['qty']
            val = data['val']

            # Check for residue in either qty or value
            if abs(val) > 0.001 or abs(qty) > 0.001:
                target_wh_name = self.env['stock.warehouse'].browse(target_wh_id).name if target_wh_id else 'N/A'

                flush_desc = 'FIFO Reset Flush (Reset Date: %s) - WH: %s' % (
                    reset_dt.date() if reset_dt else 'N/A',
                    target_wh_name
                )

                prod_rec = self.env['product.product'].browse(prod_id)

                # 1) สร้าง SVL counter entry
                new_svl = self.env['stock.valuation.layer'].create({
                    'product_id': prod_id,
                    'company_id': self.env.company.id,
                    'quantity': -qty,
                    'value': -val,
                    'description': flush_desc,
                    'warehouse_id': target_wh_id,
                })
                # Force SVL create_date = reset_dt
                if reset_dt:
                    self.env.cr.execute(
                        "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
                        (reset_dt, new_svl.id),
                    )
                # 2) สร้าง journal entry เพื่อ offset GL (เฉพาะกรณีที่มูลค่าไม่เป็นศูนย์)
                if abs(val) > 0.001:
                    self._create_flush_account_move(prod_rec, val, flush_desc, new_svl, reset_dt=reset_dt)

                flushed_count += 1

        _logger.info("FIFO Reset: Flushed SVL for %d product/warehouse combinations.", flushed_count)

    def _create_flush_account_move(self, product, val, description, svl, reset_dt=False):
        """สร้าง journal entry สำหรับ flush stock valuation ออกจาก GL โดยใช้วันที่ reset."""
        accounts = product.product_tmpl_id.get_product_accounts()
        stock_valuation_account = accounts.get('stock_valuation')
        stock_journal = accounts.get('stock_journal')
        expense_account = accounts.get('expense') or accounts.get('stock_output')

        if not stock_valuation_account or not stock_journal:
            _logger.warning(
                "FIFO Reset: Skipped creating Journal Entry for product '%s' "
                "because stock valuation account or journal is missing (Manual Valuation mode).",
                product.display_name
            )
            return

        entry_date = reset_dt.date() if reset_dt else fields.Date.today()

        if val > 0:
            debit_account = expense_account or stock_valuation_account
            credit_account = stock_valuation_account
        else:
            debit_account = stock_valuation_account
            credit_account = expense_account or stock_valuation_account
            val = abs(val)

        if not debit_account or not credit_account:
            raise exceptions.UserError(_(
                "FIFO Reset ABORTED: Missing debit/credit account for product '%s'. "
                "Please check the product category accounting configuration."
            ) % product.display_name)

        move_vals = {
            'journal_id': stock_journal.id,
            'date': entry_date,
            'ref': description,
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': val,
                    'credit': 0.0,
                    'name': description,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': val,
                    'name': description,
                }),
            ]
        }
        try:
            account_move = self.env['account.move'].sudo().create(move_vals)
            account_move.sudo().action_post()
            svl.sudo().write({'account_move_id': account_move.id})
        except Exception as e:
            raise exceptions.UserError(_(
                "FIFO Reset ABORTED: Failed to create/post journal entry for product '%s': %s"
            ) % (product.display_name, str(e)))

    def _validate_fifo(self, warehouses=None):
        """Step Final: Validate FIFO Cleanliness — ตรวจ SVL รวมเฉพาะคลังที่ถูกรีเซ็ตหลัง flush"""
        domain = [('company_id', '=', self.env.company.id)]
        if warehouses:
            domain += ['|', ('warehouse_id', 'in', warehouses.ids), ('warehouse_id', '=', False)]
            
        svl = self.env['stock.valuation.layer'].search(domain)
        total_qty = sum(svl.mapped('quantity'))
        total_value = sum(svl.mapped('value'))
        
        if abs(total_qty) > 0.001 or abs(total_value) > 0.001:
            raise exceptions.UserError(_(
                "FIFO Validate Failed! Selected warehouses' valuation layer left with QTY: %s, Value: %s"
            ) % (total_qty, total_value))
