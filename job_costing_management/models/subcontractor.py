# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import models, fields, api
from datetime import timedelta


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_subcontractor = fields.Boolean(string='Is Subcontractor', default=False)
    subcontractor_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company')
    ], string='Subcontractor Type', default='company')
    
    # Subcontractor specific fields
    trade_license = fields.Char(string='Trade License')
    license_expiry = fields.Date(string='License Expiry Date')
    specialization_ids = fields.Many2many('job.type', string='Specializations')
    rating = fields.Selection([
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐')
    ], string='Rating')
    
    # Contact details
    contact_person = fields.Char(string='Contact Person')
    emergency_contact = fields.Char(string='Emergency Contact')
    
    # Project relations
    project_ids = fields.Many2many('project.project', 'project_subcontractor_rel', 
                                  'partner_id', 'project_id', 
                                  string='Projects')
    
    # Statistics
    project_count = fields.Integer(string='Projects', compute='_compute_project_count', store=True)
    total_contract_value = fields.Float(string='Total Contract Value', compute='_compute_contract_stats', store=True)
    completed_projects = fields.Integer(string='Completed Projects', compute='_compute_contract_stats', store=True)

    @api.model
    def default_get(self, fields_list):
        """Override default_get to set subcontractor defaults when context indicates."""
        defaults = super(ResPartner, self).default_get(fields_list)
        
        # If we're in subcontractor context, set appropriate defaults
        if self.env.context.get('default_is_subcontractor'):
            defaults.update({
                'is_subcontractor': True,
                'supplier_rank': 1,
                'is_company': True,
                'subcontractor_type': 'company'
            })
        
        return defaults
    
    @api.depends('project_ids')
    def _compute_project_count(self):
        for record in self:
            record.project_count = len(record.project_ids)
    
    @api.depends('project_ids')
    def _compute_contract_stats(self):
        for record in self:
            projects = record.project_ids
            # Use a safer approach to get contract value - check if field exists
            if hasattr(projects, 'contract_amount'):
                record.total_contract_value = sum(projects.mapped('contract_amount'))
            else:
                # Fallback to project planned costs or budget if contract_amount doesn't exist
                record.total_contract_value = sum(projects.mapped('planned_amount') or [0])
            
            # More flexible stage checking for completed projects
            completed_stages = ['done', 'completed', 'finished', 'closed']
            record.completed_projects = len(projects.filtered(
                lambda p: p.stage_id and p.stage_id.name.lower() in completed_stages
            ))
    
    def action_view_projects(self):
        return {
            'name': 'Projects',
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.project_ids.ids)],
        }

    @api.model
    def create(self, vals):
        """Override create to ensure subcontractor flag is set correctly."""
        # If we're creating from subcontractor context, ensure the flag is set
        if self.env.context.get('default_is_subcontractor'):
            vals['is_subcontractor'] = True
        
        # Set supplier_rank if creating a subcontractor
        if vals.get('is_subcontractor') and 'supplier_rank' not in vals:
            vals['supplier_rank'] = 1
            
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        """Override write to maintain consistency."""
        # If setting is_subcontractor to True, also set supplier_rank
        if vals.get('is_subcontractor'):
            for record in self:
                if record.supplier_rank == 0:
                    vals['supplier_rank'] = 1
                    break
            
        return super(ResPartner, self).write(vals)

    def action_set_as_subcontractor(self):
        """Manual action to set partner as subcontractor."""
        vals = {
            'is_subcontractor': True,
            'supplier_rank': max(self.supplier_rank, 1)
        }
        
        # If not already a company, suggest making it a company
        if not self.is_company:
            vals['is_company'] = True
            
        # Set default subcontractor type if not set
        if not self.subcontractor_type:
            vals['subcontractor_type'] = 'company'
            
        self.write(vals)
        
        # Force refresh computed fields and commit
        self.env.invalidate_all()
        
        # Trigger recomputation of stored fields
        self._compute_project_count()
        self._compute_contract_stats()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.name} has been set as subcontractor. Please refresh the subcontractor list.',
                'title': 'Success',
                'type': 'success',
                'sticky': True,
            }
        }

    def action_remove_subcontractor_status(self):
        """Manual action to remove subcontractor status."""
        self.write({'is_subcontractor': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.name} is no longer a subcontractor.',
                'type': 'info',
            }
        }

    def action_open_subcontractor_form(self):
        """Open the subcontractor-specific form view."""
        return {
            'name': 'Subcontractor',
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('job_costing_management.view_subcontractor_form').id,
            'target': 'current',
        }

    @api.model 
    def get_subcontractors_by_specialization(self, specialization_name):
        """Get all subcontractors with a specific specialization."""
        specialization = self.env['job.type'].search([('name', '=', specialization_name)], limit=1)
        if specialization:
            return self.search([
                ('is_subcontractor', '=', True),
                ('specialization_ids', 'in', specialization.ids)
            ])
        return self.browse()

    @api.model
    def get_available_subcontractors(self, project_id=None):
        """Get subcontractors available for assignment (not overloaded)."""
        # Check license expiry
        today = fields.Date.context_today(self)
        domain = [
            ('is_subcontractor', '=', True),
            '|',
            ('license_expiry', '=', False),
            ('license_expiry', '>', today)
        ]
        
        return self.search(domain)

    def get_performance_rating(self):
        """Calculate performance rating based on completed projects."""
        if self.project_count == 0:
            return 0
        completion_rate = self.completed_projects / self.project_count
        return min(5, max(1, int(completion_rate * 5) + 1))

    @api.model
    def send_license_expiry_reminders(self):
        """Cron job method to send license expiry reminders."""
        # Find subcontractors with licenses expiring in next 30 days
        expiry_date = fields.Date.context_today(self) + timedelta(days=30)
        expiring_licenses = self.search([
            ('is_subcontractor', '=', True),
            ('license_expiry', '!=', False),
            ('license_expiry', '<=', expiry_date)
        ])
        
        for subcontractor in expiring_licenses:
            # You can implement email notification here
            # For now, just log a message
            subcontractor.message_post(
                body=f"License expiry reminder: {subcontractor.trade_license} expires on {subcontractor.license_expiry}",
                subject="License Expiry Reminder"
            )
        
        return True

    @api.model
    def action_debug_subcontractors(self):
        """Debug method to check existing subcontractors."""
        subcontractors = self.search([('is_subcontractor', '=', True)])
        all_partners = self.search([])
        message = f"Found {len(subcontractors)} subcontractors out of {len(all_partners)} total partners:\n"
        for sc in subcontractors:
            message += f"- {sc.name} (ID: {sc.id}, is_subcontractor: {sc.is_subcontractor})\n"
        
        # Also check recent partners that might be subcontractors
        recent_partners = self.search([], order='create_date desc', limit=10)
        message += f"\nRecent 10 partners:\n"
        for partner in recent_partners:
            message += f"- {partner.name} (ID: {partner.id}, is_subcontractor: {partner.is_subcontractor}, supplier_rank: {partner.supplier_rank})\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subcontractor Debug Info',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }

    @api.model
    def action_fix_subcontractor_records(self):
        """Helper method to fix existing subcontractor records that might not be showing."""
        # Find partners that might be subcontractors but don't have the flag set
        partners_with_subcontractor_data = self.search([
            '|', '|', '|', '|',
            ('trade_license', '!=', False),
            ('subcontractor_type', '!=', False),
            ('specialization_ids', '!=', False),
            ('contact_person', '!=', False),
            ('emergency_contact', '!=', False)
        ])
        
        # Also find partners that were manually marked as suppliers
        potential_subcontractors = self.search([
            ('supplier_rank', '>', 0),
            ('is_subcontractor', '=', False)
        ])
        
        all_candidates = partners_with_subcontractor_data | potential_subcontractors
        
        fixed_count = 0
        for partner in all_candidates:
            if not partner.is_subcontractor:
                partner.write({
                    'is_subcontractor': True,
                    'supplier_rank': max(partner.supplier_rank, 1)
                })
                fixed_count += 1
        
        # Also force refresh computed fields for all subcontractors
        all_subcontractors = self.search([('is_subcontractor', '=', True)])
        for sc in all_subcontractors:
            sc._compute_project_count()
            sc._compute_contract_stats()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subcontractor Records Fixed',
                'message': f'Fixed {fixed_count} partner records to show as subcontractors.\nTotal subcontractors now: {len(all_subcontractors)}',
                'type': 'success',
                'sticky': True,
            }
        }

    @api.model
    def action_refresh_subcontractor_list(self):
        """Force refresh subcontractor list and clear cache."""
        # Clear all cache
        self.env.invalidate_all()
        
        # Force recompute all subcontractor computed fields
        subcontractors = self.search([('is_subcontractor', '=', True)])
        for sc in subcontractors:
            sc._compute_project_count()
            sc._compute_contract_stats()
        
        # Commit changes
        self.env.cr.commit()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subcontractors (Refreshed)',
            'res_model': 'res.partner',
            'view_mode': 'tree,form',
            'domain': [('is_subcontractor', '=', True)],
            'context': {},
            'target': 'current',
        }

    @api.model
    def create_test_subcontractors(self):
        """Create test subcontractors for debugging."""
        test_data = [
            {
                'name': 'ทดสอบ บริษัทรับเหมา จำกัด',
                'is_company': True,
                'is_subcontractor': True,
                'supplier_rank': 1,
                'subcontractor_type': 'company',
                'trade_license': 'TC-TEST-001',
                'contact_person': 'คุณสมชาย ทดสอบ',
                'phone': '02-123-4567',
                'email': 'test@contractor.com',
                'rating': '4'
            },
            {
                'name': 'ช่างไฟฟ้า ทดสอบ',
                'is_company': False,
                'is_subcontractor': True,
                'supplier_rank': 1,
                'subcontractor_type': 'individual',
                'contact_person': 'คุณสมศักดิ์ ช่างไฟ',
                'phone': '089-987-6543',
                'email': 'somsakelec@gmail.com',
                'rating': '5'
            }
        ]
        
        created_ids = []
        for data in test_data:
            # Check if already exists
            existing = self.search([('name', '=', data['name'])], limit=1)
            if not existing:
                partner = self.create(data)
                created_ids.append(partner.id)
                
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ทดสอบ Subcontractors',
                'message': f'สร้าง subcontractors ทดสอบแล้ว {len(created_ids)} รายการ',
                'type': 'success',
                'sticky': True,
            }
        }

    @api.model
    def check_subcontractor_status(self):
        """Check current subcontractor status in the system."""
        # Count all partners
        total_partners = self.search_count([])
        
        # Count subcontractors
        subcontractors = self.search([('is_subcontractor', '=', True)])
        subcontractor_count = len(subcontractors)
        
        # Count suppliers
        suppliers = self.search([('supplier_rank', '>', 0)])
        supplier_count = len(suppliers)
        
        # Get recent partners with subcontractor fields
        recent_with_sub_fields = self.search([
            '|', '|', '|', 
            ('trade_license', '!=', False),
            ('subcontractor_type', '!=', False),
            ('contact_person', '!=', False),
            ('is_subcontractor', '=', True)
        ], limit=20, order='write_date desc')
        
        message = f"""สถานะ Subcontractor ในระบบ:
        
📊 สถิติรวม:
- Partners ทั้งหมด: {total_partners}
- Subcontractors: {subcontractor_count}
- Suppliers: {supplier_count}

📋 Subcontractors ที่มีอยู่:"""
        
        for sc in subcontractors:
            message += f"\n- {sc.name} (ID: {sc.id}, Type: {sc.subcontractor_type or 'ไม่ระบุ'})"
            
        if recent_with_sub_fields:
            message += f"\n\n🔍 Partners ล่าสุดที่มีข้อมูล Subcontractor:"
            for p in recent_with_sub_fields[:5]:
                message += f"\n- {p.name} (is_subcontractor: {p.is_subcontractor})"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สถานะ Subcontractor',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }

    @api.model
    def fix_existing_subcontractor_data(self):
        """Fix existing subcontractor data that has is_subcontractor = False"""
        # Find partners with subcontractor names or data but flag is False
        subcontractor_names = [
            'Bangkok Construction Co., Ltd.',
            'Thai Electric Service', 
            'Kittisak Plumbing Expert',
            'ทดสอบ บริษัทรับเหมา จำกัด',
            'ช่างไฟฟ้า ทดสอบ'
        ]
        
        # Also search for any partner that has subcontractor-related data
        partners_to_fix = self.search([
            '|', '|', '|',
            ('name', 'in', subcontractor_names),
            ('trade_license', '!=', False),
            ('subcontractor_type', '!=', False),
            ('contact_person', '!=', False)
        ])
        
        # Also check for partners with "Sub" in name
        sub_partners = self.search([('name', 'ilike', 'sub')])
        partners_to_fix = partners_to_fix | sub_partners
        
        fixed_count = 0
        fixed_names = []
        
        for partner in partners_to_fix:
            if not partner.is_subcontractor:
                vals = {
                    'is_subcontractor': True,
                    'supplier_rank': max(partner.supplier_rank, 1)
                }
                
                # Set default subcontractor type if not set
                if not partner.subcontractor_type:
                    vals['subcontractor_type'] = 'company' if partner.is_company else 'individual'
                
                partner.write(vals)
                fixed_count += 1
                fixed_names.append(partner.name)
        
        # Force refresh computed fields
        if fixed_count > 0:
            self.env.invalidate_all()
            for partner in partners_to_fix:
                if partner.is_subcontractor:
                    partner._compute_project_count()
                    partner._compute_contract_stats()
        
        # Get final count
        final_subcontractors = self.search([('is_subcontractor', '=', True)])
        
        message = f"""แก้ไขข้อมูล Subcontractor เสร็จสิ้น:

✅ แก้ไขแล้ว {fixed_count} รายการ:
"""
        for name in fixed_names[:10]:  # Show first 10
            message += f"- {name}\n"
            
        if len(fixed_names) > 10:
            message += f"... และอีก {len(fixed_names) - 10} รายการ\n"
            
        message += f"\n📊 สถิติหลังแก้ไข:\n- Subcontractors ทั้งหมด: {len(final_subcontractors)}"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'แก้ไขข้อมูล Subcontractor',
                'message': message,
                'type': 'success',
                'sticky': True,
            }
        }

    @api.model
    def emergency_sql_fix_subcontractors(self):
        """Emergency SQL fix - direct database update to bypass any validation issues"""
        try:
            # Get known subcontractor names
            known_names = [
                'Bangkok Construction Co., Ltd.',
                'Thai Electric Service', 
                'Kittisak Plumbing Expert',
                'ทดสอบ บริษัทรับเหมา จำกัด',
                'ช่างไฟฟ้า ทดสอบ',
                'Sub test1'
            ]
            
            # First, let's check the current state
            self.env.cr.execute("""
                SELECT COUNT(*) FROM res_partner WHERE is_subcontractor = true
            """)
            result = self.env.cr.fetchone()
            before_count = result[0] if result else 0
            
            # Direct SQL update for known names
            updates_made = 0
            for name in known_names:
                self.env.cr.execute("""
                    UPDATE res_partner 
                    SET is_subcontractor = true, 
                        supplier_rank = GREATEST(COALESCE(supplier_rank, 0), 1),
                        write_date = NOW(),
                        write_uid = %s
                    WHERE name = %s AND (is_subcontractor = false OR is_subcontractor IS NULL)
                """, (self.env.uid, name))
                updates_made += self.env.cr.rowcount
            
            # Update partners with subcontractor-related fields
            self.env.cr.execute("""
                UPDATE res_partner 
                SET is_subcontractor = true, 
                    supplier_rank = GREATEST(COALESCE(supplier_rank, 0), 1),
                    write_date = NOW(),
                    write_uid = %s
                WHERE (trade_license IS NOT NULL OR 
                       subcontractor_type IS NOT NULL OR 
                       contact_person IS NOT NULL) 
                AND (is_subcontractor = false OR is_subcontractor IS NULL)
            """, (self.env.uid,))
            updates_made += self.env.cr.rowcount
            
            # Update partners with 'sub' or 'contract' in name
            self.env.cr.execute("""
                UPDATE res_partner 
                SET is_subcontractor = true, 
                    supplier_rank = GREATEST(COALESCE(supplier_rank, 0), 1),
                    subcontractor_type = CASE 
                        WHEN is_company = true THEN 'company'
                        ELSE 'individual'
                    END,
                    write_date = NOW(),
                    write_uid = %s
                WHERE (LOWER(name) LIKE '%%sub%%' OR 
                       LOWER(name) LIKE '%%contract%%' OR
                       LOWER(name) LIKE '%%construct%%')
                AND (is_subcontractor = false OR is_subcontractor IS NULL)
            """, (self.env.uid,))
            updates_made += self.env.cr.rowcount
            
            # Commit the transaction
            self.env.cr.commit()
            
            # Check final count
            self.env.cr.execute("""
                SELECT COUNT(*) FROM res_partner WHERE is_subcontractor = true
            """)
            result = self.env.cr.fetchone()
            after_count = result[0] if result else 0
            
            # Get list of subcontractors
            self.env.cr.execute("""
                SELECT name, id FROM res_partner 
                WHERE is_subcontractor = true 
                ORDER BY write_date DESC 
                LIMIT 20
            """)
            subcontractors = self.env.cr.fetchall()
            
            # Clear cache to force reload
            self.env.invalidate_all()
            
            message = f"""🚨 Emergency SQL Fix เสร็จสิ้น:

📊 ผลลัพธ์:
- ก่อนแก้ไข: {before_count} subcontractors
- หลังแก้ไข: {after_count} subcontractors
- Updates made: {updates_made} records
- เพิ่มขึ้น: {after_count - before_count} รายการ

📋 Subcontractors ล่าสุด (20 รายการแรก):"""
            
            if subcontractors:
                for name, partner_id in subcontractors:
                    message += f"\n- {name} (ID: {partner_id})"
            else:
                message += "\n- ไม่มี subcontractors ในระบบ"
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🚨 Emergency SQL Fix',
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            # Rollback on error
            self.env.cr.rollback()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error in SQL Fix',
                    'message': f'Error occurred: {str(e)}\nTraceback: {type(e).__name__}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def check_database_constraints(self):
        """Check if there are any database constraints or triggers affecting is_subcontractor"""
        try:
            # Check table structure
            self.env.cr.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'res_partner' 
                AND column_name IN ('is_subcontractor', 'supplier_rank', 'subcontractor_type')
            """)
            columns = self.env.cr.fetchall()
            
            # Check constraints
            self.env.cr.execute("""
                SELECT constraint_name, constraint_type 
                FROM information_schema.table_constraints 
                WHERE table_name = 'res_partner'
                AND constraint_type IN ('CHECK', 'FOREIGN KEY')
            """)
            constraints = self.env.cr.fetchall()
            
            # Test a direct update on one record
            self.env.cr.execute("""
                SELECT id, name, is_subcontractor, supplier_rank 
                FROM res_partner 
                WHERE name = 'Sub test1' 
                LIMIT 1
            """)
            test_record = self.env.cr.fetchone()
            
            message = f"""🔍 Database Constraints Check:

📋 Columns Structure:"""
            for col in columns:
                message += f"\n- {col[0]}: {col[1]}, nullable={col[2]}, default={col[3]}"
                
            message += f"\n\n🔒 Constraints:"
            for const in constraints:
                message += f"\n- {const[0]}: {const[1]}"
                
            if test_record:
                message += f"\n\n🎯 Test Record (Sub test1):\n- ID: {test_record[0]}\n- Name: {test_record[1]}\n- is_subcontractor: {test_record[2]}\n- supplier_rank: {test_record[3]}"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🔍 Database Check',
                    'message': message,
                    'type': 'info',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Database Check Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def debug_menu_issue(self):
        """Debug why the subcontractor menu is not showing data"""
        try:
            # Check current subcontractor count
            self.env.cr.execute("SELECT COUNT(*) FROM res_partner WHERE is_subcontractor = true")
            result = self.env.cr.fetchone()
            db_count = result[0] if result else 0
            
            # Check using ORM
            orm_subcontractors = self.search([('is_subcontractor', '=', True)])
            orm_count = len(orm_subcontractors)
            
            # Check cache status
            self.env.invalidate_all()
            orm_after_invalidate = self.search([('is_subcontractor', '=', True)])
            orm_after_count = len(orm_after_invalidate)
            
            # Get sample data from both methods
            self.env.cr.execute("""
                SELECT id, name, is_subcontractor, supplier_rank 
                FROM res_partner 
                WHERE is_subcontractor = true 
                LIMIT 5
            """)
            db_samples = self.env.cr.fetchall()
            
            # Check menu action domain
            try:
                menu_action = self.env.ref('job_costing_management.action_subcontractor_list')
                action_domain = menu_action.domain if hasattr(menu_action, 'domain') else 'No domain'
            except:
                action_domain = 'Menu action not found'
            
            # Test direct domain search
            test_search = self.search([('is_subcontractor', '=', True)], limit=5)
            
            message = f"""🔍 Debug Menu Issue:

📊 Count Comparison:
- Database direct: {db_count} subcontractors
- ORM search: {orm_count} subcontractors  
- ORM after cache clear: {orm_after_count} subcontractors

📋 Sample from Database:"""
            
            for record in db_samples:
                message += f"\n- ID:{record[0]} {record[1]} (is_sub:{record[2]}, rank:{record[3]})"
                
            message += f"\n\n📋 Sample from ORM ({len(test_search)} found):"
            for partner in test_search:
                message += f"\n- ID:{partner.id} {partner.name} (is_sub:{partner.is_subcontractor})"
                
            message += f"\n\n🎯 Menu Action Domain: {action_domain}"
            
            # Check for any access rights issues
            try:
                self.check_access_rights('read')
                access_status = "✅ Read access OK"
            except Exception as e:
                access_status = f"❌ Access issue: {str(e)}"
                
            message += f"\n\n🔐 Access Rights: {access_status}"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🔍 Debug Menu Issue',
                    'message': message,
                    'type': 'info',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Debug Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def force_refresh_and_reload(self):
        """Force complete refresh of subcontractor data and clear all caches"""
        try:
            # Clear all caches
            self.env.invalidate_all()
            self.env.registry.clear_caches()
            
            # Force database commit
            self.env.cr.commit()
            
            # Recompute all stored fields for subcontractors
            subcontractors = self.search([('is_subcontractor', '=', True)])
            if subcontractors:
                subcontractors._compute_project_count()
                subcontractors._compute_contract_stats()
                
            # Force another commit
            self.env.cr.commit()
            
            # Get final count
            final_count = len(self.search([('is_subcontractor', '=', True)]))
            
            return {
                'type': 'ir.actions.act_window',
                'name': f'All Subcontractors (Total: {final_count})',
                'res_model': 'res.partner',
                'view_mode': 'tree,form',
                'domain': [('is_subcontractor', '=', True)],
                'context': {'search_default_subcontractor': 1},
                'target': 'current',
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Force Refresh Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def emergency_reset_cache_and_check(self):
        """Emergency reset cache and check subcontractor visibility"""
        try:
            # Step 1: Clear all possible caches
            self.env.invalidate_all()
            self.env.registry.clear_caches()
            
            # Step 2: Force database sync
            self.env.cr.commit()
            
            # Step 3: Check database directly
            self.env.cr.execute("SELECT COUNT(*) FROM res_partner WHERE is_subcontractor = true")
            db_count = self.env.cr.fetchone()[0]
            
            # Step 4: Try ORM search
            try:
                orm_partners = self.search([('is_subcontractor', '=', True)], limit=10)
                orm_count = len(orm_partners)
                orm_names = [p.name for p in orm_partners[:5]]
            except Exception as e:
                orm_count = f"Error: {str(e)}"
                orm_names = []
            
            # Step 5: Try different search approaches
            try:
                # Search with different domain formats
                alt_search1 = self.search([('is_subcontractor', '!=', False)], limit=10)
                alt_count1 = len(alt_search1)
                
                alt_search2 = self.search([('is_subcontractor', 'in', [True])], limit=10)
                alt_count2 = len(alt_search2)
                
                # Search all partners and filter
                all_partners = self.search([], limit=50)
                filtered_partners = all_partners.filtered(lambda p: p.is_subcontractor)
                filtered_count = len(filtered_partners)
                
            except Exception as e:
                alt_count1 = alt_count2 = filtered_count = f"Error: {str(e)}"
            
            # Step 6: Get sample database records directly
            self.env.cr.execute("""
                SELECT id, name, is_subcontractor, supplier_rank 
                FROM res_partner 
                WHERE is_subcontractor = true 
                LIMIT 5
            """)
            db_samples = self.env.cr.fetchall()
            
            message = f"""🚨 Emergency Cache Reset & Check:

📊 Counts:
- Database direct: {db_count}
- ORM search (=): {orm_count}
- ORM search (!=): {alt_count1}
- ORM search (in): {alt_count2}
- Filtered from all: {filtered_count}

📋 Database samples:"""
            
            for sample in db_samples:
                message += f"\n- ID:{sample[0]} {sample[1]} (is_sub:{sample[2]})"
            
            if orm_names:
                message += f"\n\n📋 ORM found names:"
                for name in orm_names:
                    message += f"\n- {name}"
            
            # If ORM finds nothing but DB has data, there's a serious cache/sync issue
            if db_count > 0 and orm_count == 0:
                message += f"\n\n❌ CRITICAL: Database has {db_count} records but ORM finds 0!"
                message += f"\nThis indicates a serious cache or model sync issue."
                
                # Try to force model reload
                try:
                    self.env['res.partner'].sudo().invalidate_cache()
                    message += f"\n✅ Forced model cache invalidation"
                except:
                    message += f"\n❌ Failed to invalidate model cache"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🚨 Cache Reset & Check',
                    'message': message,
                    'type': 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Reset Check Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def force_restart_module_view(self):
        """Force restart module to reload views and data"""
        try:
            # Clear everything possible
            self.env.invalidate_all()
            self.env.registry.clear_caches()
            
            # Force commit
            self.env.cr.commit()
            
            # Get direct count
            self.env.cr.execute("SELECT COUNT(*) FROM res_partner WHERE is_subcontractor = true")
            db_count = self.env.cr.fetchone()[0]
            
            # Return action that forces a fresh view
            return {
                'type': 'ir.actions.act_window',
                'name': f'🔄 Fresh Subcontractor View ({db_count} found)',
                'res_model': 'res.partner',
                'view_mode': 'tree,form',
                'domain': [('is_subcontractor', '=', True)],
                'context': {
                    'create': True,
                    'edit': True,
                    'delete': True,
                    'search_default_is_subcontractor': 1,
                    'default_is_subcontractor': True,
                },
                'target': 'current',
                'view_id': False,  # Force default view
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Force Restart Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # ...existing code...


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dest_location_id = fields.Many2one('stock.location', string='Department Location',
                                      help='Default destination location for department material requisitions')
