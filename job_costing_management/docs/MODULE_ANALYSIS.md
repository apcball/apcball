# Module Analysis: buz Project Job Costing Management for Construction

## Overview

**Module Name:** `job_costing_management`  
**Version:** 17.0.1.0.0  
**Category:** Project  
**License:** LGPL-3  
**Application:** Yes  
**Author:** Apichart Pangsalung  

## Module Purpose

This module provides comprehensive job costing management for construction projects, including:
- Job Cost Sheet management with Material, Labour, and Overhead costing
- Project and Contract management with job orders/work orders
- Material requisition and BOQ (Bill of Quantities) management
- Subcontractor management
- Integration with Purchase Orders, Vendor Bills, and Timesheets
- Cost center tracking and analytics
- Comprehensive reporting for projects, job orders, and cost sheets
- Material planning and consumption tracking
- Real-time actual vs planned cost comparison

## Dependencies

```python
[
    'base',
    'project',
    'purchase',
    'stock',
    'hr_timesheet',
    'account',
    'analytic',
    'hr',
    'mail',
    'portal',
    'contacts',
]
```

---

## Model Architecture

### Core Models Overview

The module defines **28 models** across different categories:

| Category | Models |
|----------|--------|
| **Core Costing** | `job.cost.sheet`, `job.cost.line`, `job.type`, `job.stage` |
| **Job Orders** | `job.order` |
| **Project Extension** | `project.project` (inheritance) |
| **Material Management** | `material.requisition`, `material.requisition.line`, `material.planning`, `material.consumption` |
| **BOQ Management** | `boq.boq`, `boq.line`, `boq.category`, `boq.template`, `boq.template.line` |
| **Subcontractor** | `res.partner` (inheritance), `hr.employee` (inheritance), `hr.department` (inheritance) |
| **Notes** | `job.note`, `job.note.tag` |
| **Purchase Integration** | `purchase.order` (inheritance), `purchase.order.line` (inheritance) |
| **Accounting Integration** | `account.move` (inheritance), `account.move.line` (inheritance) |
| **Timesheet Integration** | `account.analytic.line` (inheritance) |
| **Wizards** | `create.rfq.from.job.cost`, `job.cost.line.wizard`, `job.cost.line.bulk.edit.wizard`, `boq.material.requisition.wizard`, `boq.material.requisition.wizard.line` |

---

## Detailed Model Analysis

### 1. Job Cost Sheet (`job.cost.sheet`)

**Purpose:** Central model for managing all costs associated with a construction job

**Key Fields:**
- `name`: Auto-generated sequence (JCS/XXXX/YYYY)
- `project_id`: Link to project.project (required)
- `job_order_id`: Link to job.order
- `analytic_account_id`: For cost tracking
- `company_id`: Multi-company support
- `state`: Draft → Approved → Done → Cancelled

**Cost Line Collections:**
- `material_cost_ids`: One2many to `job.cost.line` (domain: cost_type='material')
- `labour_cost_ids`: One2many to `job.cost.line` (domain: cost_type='labour')
- `overhead_cost_ids`: One2many to `job.cost.line` (domain: cost_type='overhead')

**Computed Fields:**
- `total_material_cost`, `total_labour_cost`, `total_overhead_cost`, `total_cost`
- `actual_material_cost`, `actual_labour_cost`, `actual_overhead_cost`, `actual_total_cost`
- `material_variance`, `labour_variance`, `overhead_variance`, `total_variance`

**Smart Button Counters:**
- `purchase_order_count`: Count of linked POs
- `timesheet_count`: Count of linked timesheets
- `invoice_count`: Count of linked vendor bills
- `cost_lines_count`: Total number of cost lines

**Key Methods:**
- `action_sync_actual_costs()`: Manual sync of actual costs from linked documents
- `action_create_rfq()`: Wizard to create RFQ from cost sheet
- `action_view_cost_analysis()`: Detailed cost analysis view
- `action_view_all_cost_lines()`: View all cost lines

---

### 2. Job Cost Line (`job.cost.line`)

**Purpose:** Individual cost items within a job cost sheet

**Key Fields:**
- `cost_sheet_id`: Parent cost sheet (required)
- `cost_type`: Selection - material/labour/overhead
- `product_id`: Link to product.product
- `name`: Description (required)
- `planned_qty`, `actual_qty`: Quantities
- `unit_cost`, `actual_unit_cost`: Unit costs
- `total_cost`, `actual_cost`: Computed totals
- `qty_variance`, `cost_variance`: Computed variances
- `uom_id`: Unit of measure
- `analytic_account_id`: Cost tracking

**Source Tracking Fields (Duplicate Prevention):**
- `source_po_line_id`: Tracks originating PO line
- `source_timesheet_id`: Tracks originating timesheet
- `source_invoice_line_id`: Tracks originating invoice line

**Key Methods:**
- `get_or_create_cost_line()`: Factory method to prevent duplicates
- `update_actual_costs_from_purchases()`: Update costs from confirmed POs
- `_onchange_product_id()`: Auto-adjusts cost type based on product type

---

### 3. Job Order (`job.order`)

**Purpose:** Work orders/tasks within construction projects

**Key Fields:**
- `name`: Auto-generated sequence (JO/XXXX/YYYY)
- `project_id`: Link to project.project (required)
- `task_id`: Link to project.task
- `stage_id`: Link to job.stage
- `parent_job_order_id`, `child_job_order_ids`: Hierarchical structure
- `state`: Draft → In Progress → Done → Cancelled
- `priority`: 0-3 scale
- `progress`: Percentage completion
- `kanban_state`: normal/done/blocked

**Related Collections:**
- `job_cost_sheet_ids`: Linked cost sheets
- `material_planning_ids`: Material planning
- `material_consumption_ids`: Material consumption tracking
- `material_requisition_ids`: Material requisitions
- `timesheet_ids`: Linked timesheets
- `job_note_ids`: Job notes
- `boq_ids`: Bill of quantities

---

### 4. Material Requisition (`material.requisition`)

**Purpose:** Material request workflow for projects

**State Workflow:**
```
Draft → Submitted → Department Approved → Approved → Ordered → Received
                    ↓
                Rejected/Cancelled
```

**Key Fields:**
- `name`: Auto-generated sequence (MR/XXXX/YYYY)
- `project_id`, `job_order_id`, `job_cost_sheet_id`: Hierarchical links
- `employee_id`: Requestor
- `state`: Workflow state tracking
- `priority`: low/normal/high/urgent
- `boq_id`: Link to source BOQ

**Key Methods:**
- `action_create_purchase_order()`: Create POs grouped by vendor
- `action_create_picking()`: Create internal transfer

---

### 5. Bill of Quantities (BOQ) Models

#### BOQ (`boq.boq`)

**Purpose:** Detailed quantity and cost breakdown for projects

**Key Fields:**
- `name`: Auto-generated sequence (BOQXXXXX)
- `project_id`, `job_order_id`, `job_cost_sheet_id`: Hierarchical links
- `state`: Draft → Approved → Locked → Cancelled
- `title`, `description`: BOQ information
- `revision`: Version tracking

**Collections:**
- `line_ids`: BOQ lines (One2many)
- `category_ids`: BOQ categories (One2many)

**Key Methods:**
- `action_create_material_requisition()`: Create requisition from BOQ
- `action_create_job_cost_lines()`: Create cost lines from BOQ
- `copy()`: Proper duplication with line copying

#### BOQ Line (`boq.line`)

**Purpose:** Individual BOQ items

**Key Fields:**
- `boq_id`: Parent BOQ
- `product_id`: Product (required)
- `description`, `specification`: Item details
- `quantity`, `uom_id`: Quantity info
- `unit_cost`, `total_cost`: Cost info
- `waste_percentage`, `contingency_percentage`: Adjustments
- `adjusted_quantity`, `adjusted_total_cost`: Computed with adjustments

**Purchase Tracking:**
- `total_requisitioned_qty`
- `total_ordered_qty`
- `total_received_qty`
- `remaining_qty`
- `purchase_progress`

**Status:**
- pending → requisitioned → ordered → received → completed

---

### 6. BOQ Template (`boq.template`, `boq.template.line`)

**Purpose:** Reusable BOQ templates for common job types

**Features:**
- Link to `job.type`
- Copy templates to create new BOQs
- Full line structure preserved during copy

---

### 7. Material Planning & Consumption

#### Material Planning (`material.planning`)
- `job_order_id`: Linked job order
- `product_id`, `planned_qty`, `planned_date`

#### Material Consumption (`material.consumption`)
- `job_order_id`: Linked job order
- `product_id`, `consumed_qty`, `consumption_date`, `location_id`

---

### 8. Subcontractor Management

#### Extended `res.partner`:
- `subcontractor_type`: individual/company
- `trade_license`, `license_expiry`: Licensing
- `specialization_ids`: Many2many to job.type
- `rating`: 1-5 star rating
- `project_ids`: Linked projects

#### Key Methods:
- `get_subcontractors_by_specialization()`
- `get_available_subcontractors()`
- `get_performance_rating()`
- `send_license_expiry_reminders()` (cron method)

#### Extended `hr.employee` and `hr.department`:
- `dest_location_id`: Default location for requisitions

---

### 9. Job Notes (`job.note`, `job.note.tag`)

**Purpose:** Communication and documentation system

**Key Features:**
- Multiple note types: general, progress, issue, solution, meeting, instruction, observation
- Priority levels: low, normal, high, urgent
- State workflow: draft → active → resolved → archived
- Assignment to multiple users
- Follow-up notes (parent-child hierarchy)
- Private notes option
- Activity-based notifications (email disabled)

---

### 10. Integration Models

#### Purchase Order Integration (`purchase.order`)
**Extended Fields:**
- `material_requisition_id`
- `job_cost_sheet_id`
- `project_id`
- `job_order_id`

**Key Logic:**
- Auto-link to job cost sheet from material requisition
- Auto-set analytic account on PO lines

#### Purchase Order Line Integration (`purchase.order.line`)
**Extended Fields:**
- `material_requisition_line_id`
- `job_cost_sheet_id`
- `job_cost_line_id`
- `analytic_account_id`

**Key Logic:**
- Auto-create/link job cost lines when PO is created
- Duplicate prevention using `source_po_line_id`

#### Account Move Integration (`account.move`)
**Extended Fields:**
- `job_cost_sheet_id`
- `project_id`
- `job_order_id`

**Key Logic:**
- Auto-link to job cost sheet from purchase order origin

#### Account Move Line Integration (`account.move.line`)
**Extended Fields:**
- `job_cost_line_id`

**Key Logic:**
- Link to job cost line from PO line
- Link through analytic distribution

#### Timesheet Integration (`account.analytic.line`)
**Extended Fields:**
- `job_cost_line_id`
- `job_order_id`
- `project_id` (related from task)

**Key Logic:**
- Auto-link to job cost line based on analytic account
- Duplicate prevention using `source_timesheet_id`

---

## Wizard Models

### 1. Create RFQ from Job Cost (`create.rfq.from.job.cost`)

**Purpose:** Create purchase orders from selected cost lines

**Fields:**
- `job_cost_sheet_id`
- `partner_id`: Vendor
- `cost_line_ids`: Selected cost lines

**Method:**
- `action_create_rfq()`: Creates PO with lines from selected cost lines

### 2. Job Cost Line Wizard (`job.cost.line.wizard`)

**Purpose:** Bulk update cost type for selected lines

**Fields:**
- `job_cost_line_ids`: Selected lines
- `new_cost_type`: Target cost type
- `clear_product`: Option to clear product

### 3. Job Cost Line Bulk Edit Wizard (`job.cost.line.bulk.edit.wizard`)

**Purpose:** Multi-field bulk editing

**Editable Fields:**
- Cost type
- Unit cost
- Planned quantity
- Analytic account

### 4. BOQ Material Requisition Wizard (`boq.material.requisition.wizard`)

**Purpose:** Interactive material requisition creation from BOQ

**Features:**
- Two-stage wizard: Selection → Preview
- Search and filter capabilities
- Category filtering
- Quantity validation against BOQ remaining
- Summary statistics

**Fields:**
- `boq_id`, `project_id`, `job_order_id`, `job_cost_sheet_id`
- `purpose`, `required_date`, `priority`
- `search_term`, `category_filter`, `product_category_filter`
- `line_ids`: BOQ lines for selection
- Statistics fields

---

## Data Files (Sequencing)

### Sequences
1. **Job Cost Sheet:** JCS/0001/2024
2. **Material Requisition:** MR/0001/2024
3. **Job Order:** JO/0001/2024
4. **BOQ:** BOQ00001

### Default Data

**Job Stages:**
- Draft, Planning, In Progress, Under Review, Done, Cancelled

**Job Types:**
- Construction, Electrical, Plumbing, Painting, Flooring, HVAC, Roofing, Landscaping

### Cron Job

**Subcontractor License Expiry Reminders:**
- Runs weekly (every 7 days)
- Sends messages to partners with licenses expiring within 30 days

---

## Key Technical Features

### 1. Duplicate Prevention System

The module implements comprehensive duplicate prevention:

**Source Tracking Fields:**
- `source_po_line_id` on `job.cost.line`
- `source_timesheet_id` on `job.cost.line`
- `source_invoice_line_id` on `job.cost.line`

**Factory Method:**
```python
get_or_create_cost_line(cost_sheet_id, product_id, cost_type, 
                        source_po_line_id=None, source_timesheet_id=None,
                        source_invoice_line_id=None, vals=None)
```

### 2. Automatic Cost Linking

**Purchase Orders → Job Cost Lines:**
- PO creation triggers cost line search/create
- Links via product match or source tracking

**Timesheets → Job Cost Lines:**
- Timesheet creation searches for labour cost lines
- Auto-links to single labour line or task-matched line

**Invoices → Job Cost Lines:**
- Links from PO line if available
- Falls back to analytic account matching

### 3. Cost Variance Calculation

**Formulas:**
```
Quantity Variance = Actual Qty - Planned Qty
Cost Variance = Actual Cost - Planned Cost
```

**For Labour:**
- Uses `abs()` to handle negative timesheet amounts
- Timesheet unit amounts sum to actual quantity

### 4. Multi-Company Support

All major models have:
- `company_id` field
- Multi-company record rules

### 5. Access Rights Integration

The module integrates with Odoo's standard project groups:
- Inherits from `project.group_project_user`
- Inherits from `project.group_project_manager`

---

## Model Relationship Diagram (Summary)

```
project.project
    │
    ├── job.cost.sheet
    │       └── job.cost.line (material/labour/overhead)
    │
    ├── job.order
    │       ├── job.cost.sheet
    │       ├── material.requisition
    │       ├── material.planning
    │       ├── material.consumption
    │       ├── boq.boq
    │       └── account.analytic.line (timesheets)
    │
    ├── material.requisition
    │       └── material.requisition.line
    │
    ├── boq.boq
    │       ├── boq.line
    │       └── boq.category
    │
    └── res.partner (subcontractors)

purchase.order ──> job.cost.sheet
purchase.order.line ──> job.cost.line

account.move ──> job.cost.sheet
account.move.line ──> job.cost.line

account.analytic.line ──> job.cost.line
```

---

## Files Summary

| Directory | File Count | Purpose |
|-----------|------------|---------|
| `models/` | 13 | All business logic models |
| `wizard/` | 3 | Transient models for user interactions |
| `views/` | 16 | UI definitions |
| `data/` | 5 | Sequences, defaults, cron |
| `security/` | 2 | Groups, access rights, record rules |
| `reports/` | 5 | QWeb report templates |
| `demo/` | 4 | Demo data |

---

## Version History Notes

Based on code comments, the module addresses several issues:

1. **Issue #1:** Labour actual cost calculation (uses `abs()` for negative timesheet amounts)
2. **Issue #2:** Duplicate cost line prevention (implemented source tracking)
3. **Issue #3:** Overhead cost double-counting prevention (invoice vs PO source selection)
