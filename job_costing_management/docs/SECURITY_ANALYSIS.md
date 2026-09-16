# Security Analysis: Job Costing Management Module

## Overview

This document provides a comprehensive analysis of the security architecture for the `job_costing_management` module, including user groups, access rights, and record rules.

---

## Security Groups

### 1. Job Costing User (`group_job_costing_user`)

**Purpose:** Standard user access to job costing functionality

**Configuration:**
```xml
<record id="group_job_costing_user" model="res.groups">
    <field name="name">Job Costing User</field>
    <field name="category_id" ref="base.module_category_project"/>
    <field name="implied_ids" eval="[(4, ref('project.group_project_user'))]"/>
</record>
```

**Inherited Groups:**
- `project.group_project_user`: Basic project access

**Typical Permissions:**
- Read: All own records and project-related records
- Write: Own records
- Create: New records
- Delete: No delete permissions

---

### 2. Job Costing Manager (`group_job_costing_manager`)

**Purpose:** Administrative access to all job costing functionality

**Configuration:**
```xml
<record id="group_job_costing_manager" model="res.groups">
    <field name="name">Job Costing Manager</field>
    <field name="category_id" ref="base.module_category_project"/>
    <field name="implied_ids" eval="[
        (4, ref('group_job_costing_user')), 
        (4, ref('project.group_project_manager'))
    ]"/>
</record>
```

**Inherited Groups:**
- `group_job_costing_user`: All user permissions
- `project.group_project_manager`: Project management

**Typical Permissions:**
- Full CRUD access to all job costing models
- Access to configuration models

---

### 3. Material Requisition User (`group_material_requisition_user`)

**Purpose:** Access to create and manage material requisitions

**Configuration:**
```xml
<record id="group_material_requisition_user" model="res.groups">
    <field name="name">Material Requisition User</field>
    <field name="category_id" ref="base.module_category_project"/>
</record>
```

**Permissions:**
- Create material requisitions
- View own requisitions
- Edit own requisitions

---

### 4. Material Requisition Manager (`group_material_requisition_manager`)

**Purpose:** Administrative access to material requisitions

**Configuration:**
```xml
<record id="group_material_requisition_manager" model="res.groups">
    <field name="name">Material Requisition Manager</field>
    <field name="category_id" ref="base.module_category_project"/>
    <field name="implied_ids" eval="[(4, ref('group_material_requisition_user'))]"/>
</record>
```

**Inherited Groups:**
- `group_material_requisition_user`

**Permissions:**
- Full access to all material requisitions
- Approval authority

---

### 5. Department Manager (`group_department_manager`)

**Purpose:** Department-level approval authority for requisitions

**Configuration:**
```xml
<record id="group_department_manager" model="res.groups">
    <field name="name">Department Manager</field>
    <field name="category_id" ref="base.module_category_project"/>
</record>
```

**Permissions:**
- Approve requisitions from their department
- View department requisitions

---

## Group Hierarchy

```
project.group_project_manager
    └── group_job_costing_manager
            └── group_job_costing_user
                    └── project.group_project_user

group_material_requisition_manager
    └── group_material_requisition_user
```

---

## Access Rights (ir.model.access)

### Access Matrix Summary

| Model | Job Costing User | Job Costing Manager | Material Req User | Material Req Manager | Dept Manager | Base User |
|-------|-----------------|---------------------|-------------------|---------------------|--------------|-----------|
| **job.type** | CR | CRUD | - | - | - | R |
| **job.stage** | R | CRUD | - | - | - | R |
| **job.cost.sheet** | CRU | CRUD | - | - | - | R |
| **job.cost.line** | CRU | CRUD | - | - | - | R |
| **job.order** | CRU | CRUD | R | - | - | R |
| **material.planning** | CRU | CRUD | - | - | - | - |
| **material.consumption** | CRU | CRUD | - | - | - | - |
| **material.requisition** | - | - | CRUD | CRUD | CRU | - |
| **material.requisition.line** | - | - | CRU | CRUD | CRU | - |
| **job.note** | CRU | CRUD | - | - | - | - |
| **job.note.tag** | R | CRUD | - | - | - | - |
| **boq.boq** | CRU | CRUD | R | - | - | - |
| **boq.line** | CRU | CRUD | R | - | - | - |
| **boq.category** | CRU | CRUD | R | - | - | - |
| **boq.template** | CRU | CRUD | - | - | - | - |
| **boq.template.line** | CRU | CRUD | - | - | - | - |

### Legend:
- **C** = Create
- **R** = Read
- **U** = Update (Write)
- **D** = Delete (Unlink)
- **-** = No access

---

## Detailed Access Rights by Model

### Job Type (`job.type`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| base.group_user | ✅ | ❌ | ❌ | ❌ |

**Note:** Regular users can create job types but cannot delete them.

---

### Job Stage (`job.stage`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ❌ | ❌ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| base.group_user | ✅ | ❌ | ❌ | ❌ |

**Note:** Stages are configuration data; only managers can modify.

---

### Job Cost Sheet (`job.cost.sheet`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| base.group_user | ✅ | ❌ | ❌ | ❌ |

**Security Considerations:**
- Users can create and edit their own cost sheets
- Deletion restricted to managers (prevents accidental data loss)
- Record rules further restrict access

---

### Job Cost Line (`job.cost.line`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| base.group_user | ✅ | ❌ | ❌ | ❌ |

---

### Job Order (`job.order`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| group_material_requisition_user | ✅ | ❌ | ❌ | ❌ |
| base.group_user | ✅ | ❌ | ❌ | ❌ |

---

### Material Requisition (`material.requisition`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_material_requisition_user | ✅ | ✅ | ✅ | ✅ |
| group_material_requisition_manager | ✅ | ✅ | ✅ | ✅ |
| group_department_manager | ✅ | ✅ | ✅ | ❌ |

**Security Considerations:**
- Department managers cannot delete requisitions
- Users can only delete their own requisitions (enforced by record rules)

---

### Material Requisition Line (`material.requisition.line`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_material_requisition_user | ✅ | ✅ | ✅ | ❌ |
| group_material_requisition_manager | ✅ | ✅ | ✅ | ✅ |
| group_department_manager | ✅ | ✅ | ✅ | ❌ |

---

### Job Note (`job.note`)

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |

**Additional Security:**
- Private notes only visible to creator and assigned users (record rule)

---

### BOQ Models

| Model | Job Costing User | Job Costing Manager | Material Req User |
|-------|-----------------|---------------------|-------------------|
| boq.boq | CRU | CRUD | R |
| boq.line | CRU | CRUD | R |
| boq.category | CRU | CRUD | R |
| boq.template | CRU | CRUD | - |
| boq.template.line | CRU | CRUD | - |

---

### Wizard Models

All wizard models have identical access patterns:

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| group_job_costing_user | ✅ | ✅ | ✅ | ❌ |
| group_job_costing_manager | ✅ | ✅ | ✅ | ✅ |
| group_material_requisition_user | ✅ | ✅ | ✅ | ❌ |
| group_material_requisition_manager | ✅ | ✅ | ✅ | ✅ |

---

## Record Rules (ir.rule)

### 1. Job Cost Sheet Rules

#### User Access Rule
```xml
<record id="rule_job_cost_sheet_user" model="ir.rule">
    <field name="name">Job Cost Sheet: User Access</field>
    <field name="model_id" ref="model_job_cost_sheet"/>
    <field name="groups" eval="[(4, ref('group_job_costing_user'))]"/>
    <field name="domain_force">
        ['|', ('create_uid', '=', user.id), ('project_id.user_id', '=', user.id)]
    </field>
</record>
```

**Logic:** Users can see:
- Cost sheets they created
- Cost sheets for projects where they are the assigned user

#### Manager Access Rule
```xml
<record id="rule_job_cost_sheet_manager" model="ir.rule">
    <field name="name">Job Cost Sheet: Manager Access</field>
    <field name="model_id" ref="model_job_cost_sheet"/>
    <field name="groups" eval="[(4, ref('group_job_costing_manager'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
</record>
```

**Logic:** Managers can see all cost sheets (no restriction).

---

### 2. Job Order Rules

#### User Access Rule
```xml
<record id="rule_job_order_user" model="ir.rule">
    <field name="name">Job Order: User Access</field>
    <field name="model_id" ref="model_job_order"/>
    <field name="groups" eval="[(4, ref('group_job_costing_user'))]"/>
    <field name="domain_force">
        ['|', ('user_id', '=', user.id), ('project_id.user_id', '=', user.id)]
    </field>
</record>
```

**Logic:** Users can see:
- Job orders assigned to them
- Job orders in projects they manage

#### Manager Access Rule
```xml
<record id="rule_job_order_manager" model="ir.rule">
    <field name="name">Job Order: Manager Access</field>
    <field name="model_id" ref="model_job_order"/>
    <field name="groups" eval="[(4, ref('group_job_costing_manager'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
</record>
```

---

### 3. Material Requisition Rules

#### User Access Rule
```xml
<record id="rule_material_requisition_user" model="ir.rule">
    <field name="name">Material Requisition: User Access</field>
    <field name="model_id" ref="model_material_requisition"/>
    <field name="groups" eval="[(4, ref('group_material_requisition_user'))]"/>
    <field name="domain_force">
        ['|', ('employee_id.user_id', '=', user.id), ('employee_id', '=', False)]
    </field>
    <field name="perm_unlink" eval="False"/>
</record>
```

**Logic:** Users can:
- See requisitions they created (via employee user link)
- See requisitions with no employee assigned
- Cannot delete requisitions (perm_unlink=False)

#### Department Manager Access Rule
```xml
<record id="rule_material_requisition_dept_manager" model="ir.rule">
    <field name="name">Material Requisition: Department Manager Access</field>
    <field name="model_id" ref="model_material_requisition"/>
    <field name="groups" eval="[(4, ref('group_department_manager'))]"/>
    <field name="domain_force">
        ['|', ('department_id.manager_id.user_id', '=', user.id), ('department_id', '=', False)]
    </field>
    <field name="perm_unlink" eval="False"/>
</record>
```

**Logic:** Department managers can:
- See requisitions from their department
- Approve/reject requisitions
- Cannot delete requisitions

#### Manager Access Rule
```xml
<record id="rule_material_requisition_manager" model="ir.rule">
    <field name="name">Material Requisition: Manager Access</field>
    <field name="model_id" ref="model_material_requisition"/>
    <field name="groups" eval="[(4, ref('group_material_requisition_manager'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
</record>
```

**Logic:** Managers have full access to all requisitions.

---

### 4. Job Note Rules

#### User Access Rule
```xml
<record id="rule_job_note_user" model="ir.rule">
    <field name="name">Job Note: User Access</field>
    <field name="model_id" ref="model_job_note"/>
    <field name="groups" eval="[(4, ref('group_job_costing_user'))]"/>
    <field name="domain_force">
        ['|', ('user_id', '=', user.id), ('assigned_to_ids', 'in', [user.id])]
    </field>
</record>
```

**Logic:** Users can see:
- Notes they created
- Notes assigned to them

**Note:** Private notes require additional filtering.

#### Manager Access Rule
```xml
<record id="rule_job_note_manager" model="ir.rule">
    <field name="name">Job Note: Manager Access</field>
    <field name="model_id" ref="model_job_note"/>
    <field name="groups" eval="[(4, ref('group_job_costing_manager'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
</record>
```

---

### 5. Multi-Company Rules

All major models have multi-company isolation:

```xml
<!-- Job Cost Sheet -->
<record id="rule_job_cost_sheet_multi_company" model="ir.rule">
    <field name="name">Job Cost Sheet: Multi Company</field>
    <field name="model_id" ref="model_job_cost_sheet"/>
    <field name="domain_force">
        ['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]
    </field>
</record>
```

**Applied To:**
- `job.cost.sheet`
- `job.cost.line`
- `boq.boq`
- `boq.line`
- `job.order`
- `material.requisition`
- `material.requisition.line`

---

## Security Best Practices Observed

### ✅ Strengths

1. **Principle of Least Privilege**
   - Users only get access to records they need
   - Regular users cannot delete critical records

2. **Hierarchical Groups**
   - Manager groups inherit from user groups
   - Clear escalation path

3. **Multi-Company Support**
   - All models have company_id field
   - Multi-company rules prevent data leakage

4. **Record Ownership**
   - Creator-based access for many models
   - Project-based access for job costing

5. **Workflow-Based Access**
   - Department managers can only approve their department's requisitions
   - Approval workflow is enforced by record rules

### ⚠️ Areas for Improvement

1. **Private Notes**
   - No explicit record rule for `is_private` field
   - Relies on view-level filtering

2. **Timesheet Access**
   - No custom record rules for timesheet integration
   - Relies on standard hr_timesheet module rules

3. **Subcontractor Data**
   - No specific access control on subcontractor fields
   - Any user with partner access can view subcontractor info

4. **BOQ Templates**
   - No differentiation between template creators and other users
   - Templates are visible to all job costing users

---

## Data Protection Considerations

### Sensitive Data Types

1. **Financial Data**
   - Cost sheets contain planned and actual costs
   - Protected by project/cost sheet ownership rules

2. **Employee Information**
   - Material requisitions link to employees
   - Department-based access control

3. **Vendor Information**
   - Purchase orders linked to subcontractors
   - Standard partner access controls apply

4. **License Information**
   - Subcontractor trade licenses and expiry dates
   - No specific encryption or access restrictions

---

## Testing Security Configuration

### Test Scenarios

1. **User Access Test**
   ```python
   # Verify user can only see own cost sheets
   user_cost_sheets = env['job.cost.sheet'].search([])
   assert all(cs.create_uid == user or cs.project_id.user_id == user 
              for cs in user_cost_sheets)
   ```

2. **Manager Override Test**
   ```python
   # Verify manager can see all cost sheets
   all_cost_sheets = env['job.cost.sheet'].with_user(manager).search([])
   assert len(all_cost_sheets) == total_cost_sheet_count
   ```

3. **Department Manager Test**
   ```python
   # Verify dept manager can only see department requisitions
   dept_reqs = env['material.requisition'].search([])
   assert all(req.department_id.manager_id == dept_manager.employee_id 
              for req in dept_reqs)
   ```

4. **Multi-Company Test**
   ```python
   # Verify company isolation
   user_cs = env['job.cost.sheet'].search([])
   assert all(cs.company_id in user.company_ids for cs in user_cs)
   ```

---

## Security Checklist

| Item | Status | Notes |
|------|--------|-------|
| Groups defined | ✅ | 5 custom groups |
| Group hierarchy | ✅ | Proper inheritance |
| Access rights defined | ✅ | All models covered |
| Record rules defined | ✅ | Per-model + multi-company |
| Multi-company rules | ✅ | All major models |
| Least privilege | ✅ | Users limited to own data |
| Manager override | ✅ | Full access for managers |
| Workflow enforcement | ✅ | Department-based rules |
| No delete for users | ✅ | Critical models protected |
| Base group access | ✅ | Minimal public access |

---

## Recommendations

### High Priority

1. **Add Private Note Rule**
   ```xml
   <record id="rule_job_note_private" model="ir.rule">
       <field name="name">Job Note: Private Notes</field>
       <field name="model_id" ref="model_job_note"/>
       <field name="domain_force">
           ['|', ('is_private', '=', False),
            '|', ('user_id', '=', user.id),
                 ('assigned_to_ids', 'in', [user.id])]
       </field>
   </record>
   ```

### Medium Priority

2. **Add Template Ownership**
   - Add `create_uid` check to BOQ template access

3. **Add Subcontractor Privacy**
   - Consider restricting subcontractor details to managers

### Low Priority

4. **Audit Logging**
   - Consider adding audit tracking for cost sheet modifications

5. **Password Protection**
   - Consider adding password protection for sensitive reports
