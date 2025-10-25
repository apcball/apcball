# SLA Policy Implementation Plan

## File Changes Required

### 1. Models

#### buz_it_ticket/models/it_sla_policy.py
- Remove `priority` field (lines 18-23)
- Add `sla_level` field with user-friendly options
- Update `_order` to use `sla_level` instead of `priority`
- Update SQL constraint to use `sla_level` instead of `priority`
- Update `get_sla_policy` method to use `sla_level` parameter

#### buz_it_ticket/models/it_ticket.py
- Remove `priority` field (lines 61-66)
- Add `sla_level` field with same options as SLA Policy
- Update `_set_sla_policy` method to use `sla_level`
- Update activity note in `action_issue_submit` to use `sla_level`

### 2. Data Files

#### buz_it_ticket/data/sla_data.xml
- Update all SLA Policy records:
  - Remove `priority` field
  - Add `sla_level` field with appropriate values
  - Update `name` field to be more user-friendly with Thai translations

#### buz_it_ticket/data/demo_data.xml
- Update all demo tickets:
  - Remove `priority` field
  - Add `sla_level` field with appropriate values

#### buz_it_ticket/data/mail_templates.xml
- Update mail template to show SLA Policy instead of Priority

### 3. View Files

#### buz_it_ticket/views/it_config_views.xml
- Update SLA Policy form and tree views:
  - Replace `priority` field with `sla_level`

#### buz_it_ticket/views/it_ticket_views.xml
- Update ticket form view:
  - Replace `priority` field with `sla_level`
- Update list view:
  - Replace `priority` column with `sla_policy_id`
- Update kanban view:
  - Replace `priority` widget with `sla_policy_id` display
- Update search view:
  - Replace priority filters with SLA Policy filters
  - Replace priority grouping with SLA Policy grouping
- Update graph and pivot views:
  - Replace `priority` field with `sla_policy_id`

#### buz_it_ticket/views/it_ticket_separate_forms.xml
- Update all separate form views:
  - Replace `priority` field with `sla_level`

#### buz_it_ticket/views/it_ticket_kanban.xml
- Update kanban view:
  - Replace `priority` field with `sla_policy_id`

### 4. Report Files

#### buz_it_ticket/report/it_issue_report.xml
- Replace Priority display with SLA Policy

#### buz_it_ticket/report/it_access_request_report.xml
- Replace Priority display with SLA Policy

#### buz_it_ticket/report/it_purchase_request_report.xml
- Replace Priority display with SLA Policy

#### buz_it_ticket/report/it_ticket_summary_report.xml
- Update to use SLA Policy instead of Priority

### 5. Wizard Files

#### buz_it_ticket/wizards/it_ticket_summary_wizard.py
- Update to use SLA Policy instead of Priority

## Migration Script

Create a migration script to:
1. Add new `sla_level` field to both models
2. Populate `sla_level` based on existing `priority` values:
   - priority '0' → sla_level 'standard'
   - priority '1' → sla_level 'important'
   - priority '2' → sla_level 'urgent'
   - priority '3' → sla_level 'critical'
3. Update SLA Policy records to use `sla_level`
4. Remove old `priority` fields

## Testing Checklist

1. Verify SLA Policies can be created and edited
2. Verify tickets can be created with SLA levels
3. Verify SLA deadlines are calculated correctly
4. Verify all views display correctly
5. Verify search and filtering work
6. Verify reports show correct information
7. Verify mail templates show correct information
8. Verify dashboard displays correctly