# -*- coding: utf-8 -*-
"""
Migration Script: Fix PO department_id to inherit from source PR/MR
Run via Odoo shell:
    sudo -u odoo /opt/instance1/odoo17-venv/bin/python3 /opt/instance1/odoo17/odoo-bin \
        shell -c /etc/instance1.conf -d KYLD-LIVE < /srv/docker/odoo_kyld/custom-addons/biz_weekly_budget/migrate_fix_department.py
"""
import logging

_logger = logging.getLogger(__name__)

def migrate_po_departments(env):
    """Fix PO department_id based on source PR/MR documents."""
    PO = env['purchase.order'].sudo()
    PR = env['employee.purchase.requisition'].sudo()
    MR = env['material.requisition'].sudo()
    Pool = env['procurement.pool'].sudo()

    fixed_count = 0
    skipped_count = 0
    error_count = 0

    # =========================================================
    # Phase 1: Fix POs linked to PRs
    # =========================================================
    print("\n=== Phase 1: Fixing POs linked to Purchase Requisitions (PR) ===")
    pos_with_pr = PO.search([
        '|', ('requisition_order', '!=', False),
             ('pr_number', '!=', False),
        ('state', '!=', 'cancel'),
    ])
    print(f"Found {len(pos_with_pr)} POs linked to PRs")

    for po in pos_with_pr:
        try:
            pr_name = po.requisition_order or po.pr_number
            if not pr_name:
                continue

            pr = PR.search([('name', '=', pr_name)], limit=1)
            if not pr:
                continue

            source_dept = pr.dept_id or pr.department_id
            if not source_dept:
                continue

            if po.department_id != source_dept:
                old_dept = po.department_id.name if po.department_id else 'None'
                po.with_context(_budget_po_updating=True).write({
                    'department_id': source_dept.id,
                })
                print(f"  FIXED: {po.name} | PR={pr_name} | {old_dept} → {source_dept.name}")
                fixed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"  ERROR: {po.name}: {e}")
            error_count += 1

    # =========================================================
    # Phase 2: Fix POs linked to MRs
    # =========================================================
    print("\n=== Phase 2: Fixing POs linked to Material Requisitions (MR) ===")
    pos_with_mr = PO.search([
        ('material_requisition_id', '!=', False),
        ('state', '!=', 'cancel'),
    ])
    # Also find POs with origin matching MR names
    all_mr_names = MR.search([]).mapped('name')
    pos_with_mr_origin = PO.search([
        ('origin', 'in', all_mr_names),
        ('material_requisition_id', '=', False),
        ('state', '!=', 'cancel'),
    ]) if all_mr_names else PO
    pos_mr_combined = pos_with_mr | pos_with_mr_origin
    print(f"Found {len(pos_mr_combined)} POs linked to MRs")

    for po in pos_mr_combined:
        try:
            mr = po.material_requisition_id
            if not mr and po.origin:
                mr = MR.search([('name', '=', po.origin)], limit=1)
            if not mr:
                continue

            source_dept = mr.department_id
            if not source_dept:
                continue

            if po.department_id != source_dept:
                old_dept = po.department_id.name if po.department_id else 'None'
                po.with_context(_budget_po_updating=True).write({
                    'department_id': source_dept.id,
                })
                print(f"  FIXED: {po.name} | MR={mr.name} | {old_dept} → {source_dept.name}")
                fixed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"  ERROR: {po.name}: {e}")
            error_count += 1

    # =========================================================
    # Phase 3: Fix POs linked to Procurement Pools
    # =========================================================
    print("\n=== Phase 3: Fixing POs linked to Procurement Pools ===")
    pos_with_pool = PO.search([
        ('procurement_pool_id', '!=', False),
        ('state', '!=', 'cancel'),
    ])
    print(f"Found {len(pos_with_pool)} POs linked to Pools")

    for po in pos_with_pool:
        try:
            pool = po.procurement_pool_id
            if not pool:
                continue

            # Check PO lines for MR links first (line-level department)
            source_dept = False
            for po_line in po.order_line:
                mr_line = getattr(po_line, 'material_requisition_line_id', False)
                if mr_line and mr_line.requisition_id and mr_line.requisition_id.department_id:
                    source_dept = mr_line.requisition_id.department_id
                    break

            # Fallback to pool line department
            if not source_dept:
                for pline in pool.line_ids:
                    if pline.department_id:
                        source_dept = pline.department_id
                        break

            if not source_dept:
                continue

            if po.department_id != source_dept:
                old_dept = po.department_id.name if po.department_id else 'None'
                po.with_context(_budget_po_updating=True).write({
                    'department_id': source_dept.id,
                })
                print(f"  FIXED: {po.name} | Pool={pool.name} | {old_dept} → {source_dept.name}")
                fixed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"  ERROR: {po.name}: {e}")
            error_count += 1

    # =========================================================
    # Phase 4: Fix PO line departments from MR links
    # =========================================================
    print("\n=== Phase 4: Fixing PO Line departments from MR links ===")
    POLine = env['purchase.order.line'].sudo()
    po_lines_with_mr = POLine.search([
        ('material_requisition_line_id', '!=', False),
        ('order_id.state', '!=', 'cancel'),
    ])
    line_fixed = 0
    for po_line in po_lines_with_mr:
        try:
            mr_line = po_line.material_requisition_line_id
            if not mr_line or not mr_line.requisition_id:
                continue
            source_dept = mr_line.requisition_id.department_id
            if not source_dept:
                continue
            if po_line.department_id != source_dept:
                po_line.write({'department_id': source_dept.id})
                line_fixed += 1
        except Exception as e:
            error_count += 1
    print(f"  Fixed {line_fixed} PO lines")

    # =========================================================
    # Phase 5: Rebuild budget.move entries for fixed POs
    # =========================================================
    print("\n=== Phase 5: Rebuilding budget.move entries ===")
    
    # Rebuild for all non-cancelled POs to ensure consistency
    all_active_pos = PO.search([('state', '!=', 'cancel')])
    print(f"Rebuilding budget moves for {len(all_active_pos)} active POs...")
    
    batch_size = 50
    for i in range(0, len(all_active_pos), batch_size):
        batch = all_active_pos[i:i+batch_size]
        try:
            batch._update_budget_moves()
            env.cr.commit()
            print(f"  Batch {i//batch_size + 1}: {len(batch)} POs processed")
        except Exception as e:
            print(f"  ERROR in batch {i//batch_size + 1}: {e}")
            env.cr.rollback()
            # Try one by one
            for po in batch:
                try:
                    po._update_budget_moves()
                    env.cr.commit()
                except Exception as e2:
                    print(f"    ERROR: {po.name}: {e2}")
                    env.cr.rollback()

    # Rebuild MR budget moves
    print("\n  Rebuilding MR budget moves...")
    all_active_mrs = MR.search([('state', 'not in', ('draft', 'cancelled', 'cancel'))])
    for i in range(0, len(all_active_mrs), batch_size):
        batch = all_active_mrs[i:i+batch_size]
        try:
            batch._update_budget_moves()
            env.cr.commit()
            print(f"  MR Batch {i//batch_size + 1}: {len(batch)} MRs processed")
        except Exception as e:
            print(f"  ERROR in MR batch: {e}")
            env.cr.rollback()

    # Rebuild PR budget moves
    print("\n  Rebuilding PR budget moves...")
    all_active_prs = PR.search([('state', '!=', 'draft')])
    for i in range(0, len(all_active_prs), batch_size):
        batch = all_active_prs[i:i+batch_size]
        try:
            batch._update_budget_moves()
            env.cr.commit()
            print(f"  PR Batch {i//batch_size + 1}: {len(batch)} PRs processed")
        except Exception as e:
            print(f"  ERROR in PR batch: {e}")
            env.cr.rollback()

    # =========================================================
    # Summary
    # =========================================================
    print("\n" + "=" * 60)
    print(f"MIGRATION COMPLETE")
    print(f"  PO departments fixed: {fixed_count}")
    print(f"  PO departments already correct: {skipped_count}")
    print(f"  PO lines fixed: {line_fixed}")
    print(f"  Errors: {error_count}")
    print("=" * 60)

    env.cr.commit()


# Execute
migrate_po_departments(env)
