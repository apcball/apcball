# IT Ticket Fields Implementation Plan

## Overview
This document outlines the implementation plan for adding four new required fields to the Issue/Repair tickets in the IT Ticket Management System:
1. Email (requester_email)
2. ID LINE (line_id)
3. Symptoms/Issues (symptoms)
4. Computer Name (computer_name)

## Technical Specifications

### 1. Model Changes (it.ticket.py)

#### New Fields to Add:
```python
# Issue specific fields
requester_email = fields.Char('Email', required=True)
line_id = fields.Char('ID LINE', required=True)
symptoms = fields.Text('Symptoms/Issues (อาการเสีย)', required=True)
computer_name = fields.Char('Computer Name', required=True)
```

#### Validation Logic:
- These fields should only be required when `category == 'issue'`
- For other categories (access, purchase), these fields should be optional or invisible

#### Methods to Add/Modify:
- Override `create()` and `write()` methods to add validation for required fields when category is 'issue'
- Add computed property to show/hide fields based on category

### 2. View Changes (it_ticket_separate_forms.xml)

#### Issue Form View Updates:
- Add a new group section in the Issue ticket form for the required fields
- Position after the basic information section but before the description
- Make fields required only for Issue category

#### Proposed Layout:
```xml
<!-- Issue Specific Information -->
<group string="Issue Details" invisible="category != 'issue'">
    <group>
        <field name="requester_email" required="category == 'issue'" />
        <field name="line_id" required="category == 'issue'" />
    </group>
    <group>
        <field name="computer_name" required="category == 'issue'" />
    </group>
</group>
<group string="Symptoms/Issues" invisible="category != 'issue'">
    <field name="symptoms" required="category == 'issue'" placeholder="Please describe the symptoms or issues in detail..." />
</group>
```

### 3. Report Template Changes (it_issue_report.xml)

#### Report Updates:
- Add new rows to the Ticket Information table to display the new fields
- Position after the existing ticket information but before the Issue Description

#### Proposed Report Layout:
```xml
<!-- Add after line 45 in the Ticket Information table -->
<tr>
    <th>Email:</th>
    <td><span t-field="o.requester_email"/></td>
    <th>ID LINE:</th>
    <td><span t-field="o.line_id"/></td>
</tr>
<tr>
    <th>Computer Name:</th>
    <td colspan="3"><span t-field="o.computer_name"/></td>
</tr>
```

### 4. Validation Logic

#### Required Field Validation:
```python
@api.constrains('category', 'requester_email', 'line_id', 'symptoms', 'computer_name')
def _check_issue_required_fields(self):
    for ticket in self:
        if ticket.category == 'issue':
            if not ticket.requester_email:
                raise ValidationError(_('Email is required for Issue tickets'))
            if not ticket.line_id:
                raise ValidationError(_('ID LINE is required for Issue tickets'))
            if not ticket.symptoms:
                raise ValidationError(_('Symptoms/Issues is required for Issue tickets'))
            if not ticket.computer_name:
                raise ValidationError(_('Computer Name is required for Issue tickets'))
```

### 5. Email Field Considerations

#### Options for Email Field:
1. **Separate Field**: Add a new `requester_email` field as specified
2. **Related Field**: Use the employee's work email with option to override
3. **Computed Field**: Auto-populate from employee but allow override

#### Recommended Approach:
Use a separate field with default value from employee's email:
```python
requester_email = fields.Char('Email', required=True, default=lambda self: self._default_requester_email())

@api.model
def _default_requester_email(self):
    if self.employee_id and self.employee_id.work_email:
        return self.employee_id.work_email
    elif self.employee_id and self.employee_id.user_id and self.employee_id.user_id.email:
        return self.employee_id.user_id.email
    return ''
```

## Implementation Steps

1. **Model Updates**
   - Add new fields to it.ticket model
   - Add validation constraints
   - Add default value logic for email

2. **View Updates**
   - Update Issue form view with new fields
   - Add conditional visibility/requirement logic

3. **Report Updates**
   - Modify Issue report template to display new fields

4. **Testing**
   - Test form validation for Issue tickets
   - Test that fields are optional for Access/Purchase tickets
   - Test report generation with new fields
   - Test email default population

5. **Documentation**
   - Update module description if needed
   - Add field help text for user guidance

## Migration Considerations

- Existing Issue tickets will need to be updated with the new required fields
- Consider adding a data migration script to populate default values for existing tickets
- Or make fields conditionally required only for new tickets

## UI/UX Considerations

- Use appropriate field types (Char for short text, Text for symptoms)
- Add placeholder text to guide users
- Consider field order for logical data entry flow
- Use Thai labels where appropriate (อาการเสีย for symptoms)

## Security Considerations

- Ensure proper access rights for new fields
- Consider if any fields should be restricted to certain user groups
- Validate email format if needed