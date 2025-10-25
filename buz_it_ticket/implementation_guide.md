# Implementation Guide for Separate IT Ticket Forms

## Step 1: Create the New View File

Create a new file: `buz_it_ticket/views/it_ticket_separate_forms.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <!-- Issue/Repair Ticket Form View -->
        <record id="view_it_ticket_issue_form" model="ir.ui.view">
            <field name="name">it.ticket.issue.form</field>
            <field name="model">it.ticket</field>
            <field name="arch" type="xml">
                <form string="Issue/Repair Ticket">
                    <header>
                        <!-- Issue/Repair specific buttons -->
                        <button name="action_issue_submit" string="Submit Issue" type="object" 
                                invisible="state != 'draft'" class="btn-primary" />
                        <button name="action_issue_start_work" string="Start Work" type="object" 
                                invisible="state != 'submitted'" />
                        <button name="action_issue_need_info" string="Need Info" type="object" 
                                invisible="state not in ['in_progress', 'pending_info']" />
                        <button name="action_issue_resolve" string="Resolve" type="object" 
                                invisible="state not in ['in_progress', 'pending_info']" />
                        <button name="action_issue_close" string="Close Issue" type="object" 
                                invisible="state != 'resolved'" />
                        <button name="action_issue_cancel" string="Cancel" type="object" 
                                invisible="state == 'closed'" />
                        
                        <!-- Common buttons -->
                        <button name="action_record_print" string="Print Report" type="object" 
                                invisible="state == 'draft'" />
                        
                        <field name="state" widget="statusbar" 
                               statusbar_visible="draft,submitted,in_progress,pending_info,resolved,closed" />
                    </header>
                    
                    <sheet>
                        <div class="oe_button_box" name="button_box">
                            <button name="action_view_activities" type="object" class="oe_stat_button" icon="fa-clock-o"
                                    invisible="activity_ids == []" >
                                <field name="activity_ids" widget="statinfo" string="Activities" />
                            </button>
                            <button class="oe_stat_button" icon="fa-print" name="action_print_iso_report" type="object">
                                <field name="printed_count" widget="statinfo" string="Printed" />
                            </button>
                        </div>
                        
                        <div class="oe_title">
                            <h1>
                                <field name="name" readonly="1" />
                            </h1>
                        </div>
                        
                        <group>
                            <group>
                                <field name="category" readonly="1" required="1" />
                                <field name="priority" />
                                <field name="employee_id" required="1" />
                                <field name="manager_id" />
                                <field name="department_id" />
                                <field name="it_responsible_id" />
                            </group>
                            <group>
                                <field name="company_id" groups="base.group_multi_company" />
                                <field name="user_id" readonly="1" />
                                <field name="create_date" readonly="1" />
                                <field name="sla_policy_id" />
                                <field name="deadline_sla" />
                                <field name="sla_breached" widget="boolean_toggle" />
                            </group>
                        </group>
                        
                        <notebook>
                            <page string="Description">
                                <field name="description" placeholder="Describe the issue or request..." />
                                <field name="attachment_ids" widget="many2many_attachments" />
                            </page>
                            
                            <page string="SLA Tracking">
                                <group>
                                    <group>
                                        <field name="responded_at" readonly="1" />
                                        <field name="resolved_at" readonly="1" />
                                    </group>
                                    <group>
                                        <field name="ttr_respond" readonly="1" />
                                        <field name="ttr_resolve" readonly="1" />
                                    </group>
                                </group>
                            </page>
                            
                            <page string="ISO Information">
                                <group>
                                    <group>
                                        <field name="iso_doc_code" />
                                        <field name="revision" />
                                    </group>
                                    <group>
                                        <field name="printed_count" readonly="1" />
                                        <field name="printed_by" readonly="1" />
                                        <field name="printed_at" readonly="1" />
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                    
                    <div class="oe_chatter">
                        <field name="message_follower_ids" />
                        <field name="activity_ids" />
                        <field name="message_ids" />
                    </div>
                </form>
            </field>
        </record>
        
        <!-- Access Request Ticket Form View -->
        <record id="view_it_ticket_access_form" model="ir.ui.view">
            <field name="name">it.ticket.access.form</field>
            <field name="model">it.ticket</field>
            <field name="arch" type="xml">
                <form string="Access Request Ticket">
                    <header>
                        <!-- Access specific buttons -->
                        <button name="action_access_submit" string="Submit Request" type="object" 
                                invisible="state != 'draft'" class="btn-primary" />
                        <button name="action_access_manager_approve" string="Approve" type="object" 
                                invisible="state != 'waiting_manager'" />
                        <button name="action_access_manager_reject" string="Reject" type="object" 
                                invisible="state != 'waiting_manager'" />
                        <button name="action_access_start_implement" string="Start Implement" type="object" 
                                invisible="state != 'approved'" />
                        <button name="action_access_mark_done" string="Mark Done" type="object" 
                                invisible="state != 'implementing'" />
                        <button name="action_access_cancel" string="Cancel" type="object" 
                                invisible="state == 'closed'" />
                        
                        <!-- Common buttons -->
                        <button name="action_record_print" string="Print Report" type="object" 
                                invisible="state == 'draft'" />
                        
                        <field name="state" widget="statusbar" 
                               statusbar_visible="draft,waiting_manager,approved,implementing,closed" />
                    </header>
                    
                    <sheet>
                        <div class="oe_button_box" name="button_box">
                            <button name="action_view_activities" type="object" class="oe_stat_button" icon="fa-clock-o"
                                    invisible="activity_ids == []" >
                                <field name="activity_ids" widget="statinfo" string="Activities" />
                            </button>
                            <button class="oe_stat_button" icon="fa-print" name="action_print_iso_report" type="object">
                                <field name="printed_count" widget="statinfo" string="Printed" />
                            </button>
                        </div>
                        
                        <div class="oe_title">
                            <h1>
                                <field name="name" readonly="1" />
                            </h1>
                        </div>
                        
                        <group>
                            <group>
                                <field name="category" readonly="1" required="1" />
                                <field name="priority" />
                                <field name="employee_id" required="1" />
                                <field name="manager_id" />
                                <field name="department_id" />
                                <field name="it_responsible_id" />
                            </group>
                            <group>
                                <field name="company_id" groups="base.group_multi_company" />
                                <field name="user_id" readonly="1" />
                                <field name="create_date" readonly="1" />
                                <field name="sla_policy_id" />
                                <field name="deadline_sla" />
                                <field name="sla_breached" widget="boolean_toggle" />
                            </group>
                        </group>
                        
                        <notebook>
                            <page string="Description">
                                <field name="description" placeholder="Describe the access request..." />
                                <field name="attachment_ids" widget="many2many_attachments" />
                            </page>
                            
                            <page string="Access Details">
                                <group>
                                    <field name="access_template_id" />
                                </group>
                                <field name="access_line_ids">
                                    <tree editable="bottom">
                                        <field name="access_type" />
                                        <field name="name" />
                                        <field name="access_payload" />
                                        <field name="notes" />
                                    </tree>
                                </field>
                            </page>
                            
                            <page string="SLA Tracking">
                                <group>
                                    <group>
                                        <field name="responded_at" readonly="1" />
                                        <field name="resolved_at" readonly="1" />
                                    </group>
                                    <group>
                                        <field name="ttr_respond" readonly="1" />
                                        <field name="ttr_resolve" readonly="1" />
                                    </group>
                                </group>
                            </page>
                            
                            <page string="ISO Information">
                                <group>
                                    <group>
                                        <field name="iso_doc_code" />
                                        <field name="revision" />
                                    </group>
                                    <group>
                                        <field name="printed_count" readonly="1" />
                                        <field name="printed_by" readonly="1" />
                                        <field name="printed_at" readonly="1" />
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                    
                    <div class="oe_chatter">
                        <field name="message_follower_ids" />
                        <field name="activity_ids" />
                        <field name="message_ids" />
                    </div>
                </form>
            </field>
        </record>
        
        <!-- Purchase Request Ticket Form View -->
        <record id="view_it_ticket_purchase_form" model="ir.ui.view">
            <field name="name">it.ticket.purchase.form</field>
            <field name="model">it.ticket</field>
            <field name="arch" type="xml">
                <form string="Purchase Request Ticket">
                    <header>
                        <!-- Purchase specific buttons -->
                        <button name="action_purchase_submit" string="Submit Request" type="object" 
                                invisible="state != 'draft'" class="btn-primary" />
                        <button name="action_purchase_manager_approve" string="Approve" type="object" 
                                invisible="state != 'waiting_manager'" />
                        <button name="action_purchase_manager_reject" string="Reject" type="object" 
                                invisible="state != 'waiting_manager'" />
                        <button name="action_purchase_create_po" string="Create PO" type="object" 
                                invisible="state != 'waiting_it'" />
                        <button name="action_purchase_mark_received" string="Mark Received" type="object" 
                                invisible="state != 'po_created'" />
                        <button name="action_purchase_close" string="Close Purchase" type="object" 
                                invisible="state not in ['received', 'po_created']" />
                        <button name="action_purchase_cancel" string="Cancel" type="object" 
                                invisible="state == 'closed'" />
                        
                        <!-- Common buttons -->
                        <button name="action_record_print" string="Print Report" type="object" 
                                invisible="state == 'draft'" />
                        
                        <field name="state" widget="statusbar" 
                               statusbar_visible="draft,waiting_manager,waiting_it,po_created,received,closed" />
                    </header>
                    
                    <sheet>
                        <div class="oe_button_box" name="button_box">
                            <button name="action_view_purchase_order" type="object"
                                    class="oe_stat_button" icon="fa-shopping-cart"
                                    invisible="purchase_id == False" >
                                <field name="purchase_id" widget="statinfo" string="Purchase Order" />
                            </button>
                            <button name="action_view_activities" type="object" class="oe_stat_button" icon="fa-clock-o"
                                    invisible="activity_ids == []" >
                                <field name="activity_ids" widget="statinfo" string="Activities" />
                            </button>
                            <button class="oe_stat_button" icon="fa-print" name="action_print_iso_report" type="object">
                                <field name="printed_count" widget="statinfo" string="Printed" />
                            </button>
                        </div>
                        
                        <div class="oe_title">
                            <h1>
                                <field name="name" readonly="1" />
                            </h1>
                        </div>
                        
                        <group>
                            <group>
                                <field name="category" readonly="1" required="1" />
                                <field name="priority" />
                                <field name="employee_id" required="1" />
                                <field name="manager_id" />
                                <field name="department_id" />
                                <field name="it_responsible_id" />
                            </group>
                            <group>
                                <field name="company_id" groups="base.group_multi_company" />
                                <field name="user_id" readonly="1" />
                                <field name="create_date" readonly="1" />
                                <field name="sla_policy_id" />
                                <field name="deadline_sla" />
                                <field name="sla_breached" widget="boolean_toggle" />
                            </group>
                        </group>
                        
                        <notebook>
                            <page string="Description">
                                <field name="description" placeholder="Describe the purchase request..." />
                                <field name="attachment_ids" widget="many2many_attachments" />
                            </page>
                            
                            <page string="Purchase Details">
                                <field name="purchase_line_ids">
                                    <tree editable="bottom">
                                        <field name="product_id" />
                                        <field name="name" />
                                        <field name="quantity" />
                                        <field name="uom_id" />
                                        <field name="estimated_cost" />
                                        <field name="notes" />
                                    </tree>
                                </field>
                                <group>
                                    <field name="purchase_id" readonly="purchase_id != False" />
                                </group>
                            </page>
                            
                            <page string="SLA Tracking">
                                <group>
                                    <group>
                                        <field name="responded_at" readonly="1" />
                                        <field name="resolved_at" readonly="1" />
                                    </group>
                                    <group>
                                        <field name="ttr_respond" readonly="1" />
                                        <field name="ttr_resolve" readonly="1" />
                                    </group>
                                </group>
                            </page>
                            
                            <page string="ISO Information">
                                <group>
                                    <group>
                                        <field name="iso_doc_code" />
                                        <field name="revision" />
                                    </group>
                                    <group>
                                        <field name="printed_count" readonly="1" />
                                        <field name="printed_by" readonly="1" />
                                        <field name="printed_at" readonly="1" />
                                    </group>
                                </group>
                            </page>
                        </notebook>
                    </sheet>
                    
                    <div class="oe_chatter">
                        <field name="message_follower_ids" />
                        <field name="activity_ids" />
                        <field name="message_ids" />
                    </div>
                </form>
            </field>
        </record>
    </data>
</odoo>
```

## Step 2: Update the Actions File

Modify `buz_it_ticket/views/it_ticket_actions.xml`:

```xml
<!-- Update these three actions to reference the new form views -->

<record id="action_it_ticket_issue" model="ir.actions.act_window">
    <field name="name">Issue/Repair Tickets</field>
    <field name="res_model">it.ticket</field>
    <field name="view_mode">kanban,tree,form</field>
    <field name="view_id" ref="view_it_ticket_issue_form"/>  <!-- Changed to new form view -->
    <field name="domain">[('category', '=', 'issue')]</field>
    <field name="context">{'default_category': 'issue'}</field>
    <field name="help" type="html">
        <p class="o_view_nocontent_smiling_face">
            Create your first issue ticket!
        </p>
        <p>
            Report issues or repair requests through IT tickets.
        </p>
    </field>
</record>

<record id="action_it_ticket_access" model="ir.actions.act_window">
    <field name="name">Access Request Tickets</field>
    <field name="res_model">it.ticket</field>
    <field name="view_mode">kanban,tree,form</field>
    <field name="view_id" ref="view_it_ticket_access_form"/>  <!-- Changed to new form view -->
    <field name="domain">[('category', '=', 'access')]</field>
    <field name="context">{'default_category': 'access'}</field>
    <field name="help" type="html">
        <p class="o_view_nocontent_smiling_face">
            Create your first access request!
        </p>
        <p>
            Request access to systems, applications, or resources.
        </p>
    </field>
</record>

<record id="action_it_ticket_purchase" model="ir.actions.act_window">
    <field name="name">Purchase Request Tickets</field>
    <field name="res_model">it.ticket</field>
    <field name="view_mode">kanban,tree,form</field>
    <field name="view_id" ref="view_it_ticket_purchase_form"/>  <!-- Changed to new form view -->
    <field name="domain">[('category', '=', 'purchase')]</field>
    <field name="context">{'default_category': 'purchase'}</field>
    <field name="help" type="html">
        <p class="o_view_nocontent_smiling_face">
            Create your first purchase request!
        </p>
        <p>
            Request IT equipment or software purchases.
        </p>
    </field>
</record>
```

## Step 3: Update the Manifest File

Modify `buz_it_ticket/__manifest__.py`:

```python
'data': [
    'security/security.xml',
    'security/ir.model.access.csv',
    'data/sequence.xml',
    'data/sla_data.xml',
    'data/access_templates.xml',
    'data/mail_templates.xml',
    'data/cron_data.xml',
    'views/it_ticket_views.xml',
    'views/it_ticket_separate_forms.xml',  # Add this line
    'views/it_ticket_kanban.xml',
    'views/it_ticket_actions.xml',
    'views/it_dashboard_views.xml',
    'views/it_config_views.xml',
    'views/it_ticket_menu.xml',
],
```

## Step 4: Testing

After implementing these changes:

1. Restart Odoo server
2. Update the module
3. Test each ticket type:
   - Issue/Repair: Verify all buttons work and states transition correctly
   - Access Request: Verify access template and lines work properly
   - Purchase Request: Verify purchase lines and PO creation work
4. Check that the correct form opens for each menu item
5. Verify that all workflows function as expected

## Notes

1. The original form view (`view_it_ticket_form`) can still be kept as a fallback or for the "All Tickets" menu
2. The category field is set to readonly in each form since it's determined by which menu/action opens the form
3. Each form has a customized status bar showing only the relevant states for that ticket type
4. The button visibility conditions have been simplified since we know the category in each form