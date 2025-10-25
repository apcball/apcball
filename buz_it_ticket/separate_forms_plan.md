# Plan to Create Separate Form Views for IT Ticket Types

## Overview
The current IT ticket system uses a single form with conditional visibility based on the category field. This plan outlines how to create completely separate form views for each ticket type (Issue/Repair, Access Request, and Purchase Request) with different layouts and fields.

## Analysis of Current Form Structure

### Common Fields (All Ticket Types)
- Basic fields: name, category, priority, employee_id, manager_id, department_id, it_responsible_id
- Organization: company_id, user_id, create_date
- Description: description, attachment_ids
- SLA fields: sla_policy_id, deadline_sla, responded_at, resolved_at, ttr_respond, ttr_resolve, sla_breached
- ISO fields: iso_doc_code, revision, printed_count, printed_by, printed_at

### Issue/Repair Specific Fields
- No specific fields, but has a unique workflow with states: draft → submitted → in_progress → pending_info → resolved → closed
- Buttons: Submit Issue, Start Work, Need Info, Resolve, Close Issue, Cancel

### Access Request Specific Fields
- access_template_id: Template for access requests
- access_line_ids: One2many field for access request lines
- Workflow: draft → waiting_manager → approved → implementing → closed
- Buttons: Submit Request, Approve, Reject, Start Implement, Mark Done, Cancel

### Purchase Request Specific Fields
- purchase_line_ids: One2many field for purchase request lines
- purchase_id: Link to created purchase order
- Workflow: draft → waiting_manager → waiting_it → po_created → received → closed
- Buttons: Submit Request, Approve, Reject, Create PO, Mark Received, Close Purchase, Cancel

## Implementation Plan

### 1. Create Separate Form Views

#### 1.1 Issue/Repair Ticket Form (view_it_ticket_issue_form)
- Focus on problem description and resolution tracking
- Include all common fields
- Add Issue/Repair specific buttons
- Status bar should show: draft, submitted, in_progress, pending_info, resolved, closed
- Layout optimized for issue tracking

#### 1.2 Access Request Form (view_it_ticket_access_form)
- Focus on access request details
- Include all common fields
- Add access_template_id and access_line_ids fields
- Add Access Request specific buttons
- Status bar should show: draft, waiting_manager, approved, implementing, closed
- Layout optimized for access management

#### 1.3 Purchase Request Form (view_it_ticket_purchase_form)
- Focus on purchase request details
- Include all common fields
- Add purchase_line_ids and purchase_id fields
- Add Purchase Request specific buttons
- Status bar should show: draft, waiting_manager, waiting_it, po_created, received, closed
- Layout optimized for purchase tracking

### 2. Update Actions

#### 2.1 Modify action_it_ticket_issue
- Set view_id to reference view_it_ticket_issue_form
- Keep domain filter for category='issue'
- Keep context default_category='issue'

#### 2.2 Modify action_it_ticket_access
- Set view_id to reference view_it_ticket_access_form
- Keep domain filter for category='access'
- Keep context default_category='access'

#### 2.3 Modify action_it_ticket_purchase
- Set view_id to reference view_it_ticket_purchase_form
- Keep domain filter for category='purchase'
- Keep context default_category='purchase'

### 3. Update Manifest File

Add the new view file to the data section:
```xml
'data': [
    # ... existing files ...
    'views/it_ticket_separate_forms.xml',  # New file
    # ... rest of files ...
],
```

### 4. File Structure

Create a new file: `buz_it_ticket/views/it_ticket_separate_forms.xml`

This file will contain:
1. view_it_ticket_issue_form
2. view_it_ticket_access_form
3. view_it_ticket_purchase_form

## Detailed Form Specifications

### Issue/Repair Form Layout
```
Header:
- Issue-specific buttons (Submit Issue, Start Work, Need Info, Resolve, Close Issue, Cancel)
- Status bar with issue states

Sheet:
- Button box with Activities and Printed stats
- Title with ticket number
- Group 1: Category (readonly), Priority, Employee ID, Manager ID, Department ID, IT Responsible
- Group 2: Company ID, Created By, Create Date, SLA Policy, SLA Deadline, SLA Breached

Notebook:
- Page 1: Description (description field, attachments)
- Page 2: SLA Tracking (responded_at, resolved_at, ttr_respond, ttr_resolve)
- Page 3: ISO Information (iso_doc_code, revision, printed_count, printed_by, printed_at)

Chatter section
```

### Access Request Form Layout
```
Header:
- Access-specific buttons (Submit Request, Approve, Reject, Start Implement, Mark Done, Cancel)
- Status bar with access states

Sheet:
- Button box with Activities and Printed stats
- Title with ticket number
- Group 1: Category (readonly), Priority, Employee ID, Manager ID, Department ID, IT Responsible
- Group 2: Company ID, Created By, Create Date, SLA Policy, SLA Deadline, SLA Breached

Notebook:
- Page 1: Description (description field, attachments)
- Page 2: Access Details (access_template_id, access_line_ids tree)
- Page 3: SLA Tracking (responded_at, resolved_at, ttr_respond, ttr_resolve)
- Page 4: ISO Information (iso_doc_code, revision, printed_count, printed_by, printed_at)

Chatter section
```

### Purchase Request Form Layout
```
Header:
- Purchase-specific buttons (Submit Request, Approve, Reject, Create PO, Mark Received, Close Purchase, Cancel)
- Status bar with purchase states

Sheet:
- Button box with Purchase Order, Activities, and Printed stats
- Title with ticket number
- Group 1: Category (readonly), Priority, Employee ID, Manager ID, Department ID, IT Responsible
- Group 2: Company ID, Created By, Create Date, SLA Policy, SLA Deadline, SLA Breached

Notebook:
- Page 1: Description (description field, attachments)
- Page 2: Purchase Details (purchase_line_ids tree, purchase_id)
- Page 3: SLA Tracking (responded_at, resolved_at, ttr_respond, ttr_resolve)
- Page 4: ISO Information (iso_doc_code, revision, printed_count, printed_by, printed_at)

Chatter section
```

## Benefits of This Approach

1. **Better User Experience**: Each form is tailored to the specific workflow, making it easier for users to understand what information they need to provide.

2. **Cleaner Interface**: No irrelevant fields or buttons are shown for each ticket type.

3. **Improved Workflow**: The status bar and buttons are specific to each ticket type's workflow.

4. **Maintainability**: Each form view is independent, making it easier to modify one without affecting others.

5. **Future Extensibility**: New fields can be added to specific ticket types without cluttering other forms.

## Next Steps

1. Create the new view file with the three separate form views
2. Update the actions to reference the new form views
3. Update the manifest file to include the new view file
4. Test each ticket type to ensure all workflows work correctly
5. Verify that all buttons and status transitions work as expected