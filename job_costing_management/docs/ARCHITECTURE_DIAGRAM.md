# Architecture Diagrams: Job Costing Management Module

This document provides comprehensive Mermaid diagrams illustrating the architecture, relationships, and data flow of the `job_costing_management` module.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Entity Relationship Diagram](#entity-relationship-diagram)
3. [Job Cost Sheet Data Flow](#job-cost-sheet-data-flow)
4. [Material Requisition Workflow](#material-requisition-workflow)
5. [BOQ to Cost Line Flow](#boq-to-cost-line-flow)
6. [Purchase Order Integration](#purchase-order-integration)
7. [Timesheet Integration](#timesheet-integration)
8. [Invoice Integration](#invoice-integration)
9. [Class Diagram](#class-diagram)
10. [Security Model](#security-model)

---

## High-Level Architecture

```mermaid
flowchart TB
    subgraph "External Modules"
        BASE[base]
        PROJECT[project]
        PURCHASE[purchase]
        STOCK[stock]
        TIMESHEET[hr_timesheet]
        ACCOUNT[account]
        ANALYTIC[analytic]
        HR[hr]
        MAIL[mail]
    end

    subgraph "Job Costing Management"
        direction TB
        
        subgraph "Core Models"
            JCS[job.cost.sheet]
            JCL[job.cost.line]
            JO[job.order]
            JT[job.type]
            JS[job.stage]
        end
        
        subgraph "Material Management"
            MR[material.requisition]
            MRL[material.requisition.line]
            MP[material.planning]
            MC[material.consumption]
        end
        
        subgraph "BOQ Management"
            BOQ[boq.boq]
            BL[boq.line]
            BC[boq.category]
            BT[boq.template]
        end
        
        subgraph "Integration"
            PO[purchase.order]
            POL[purchase.order.line]
            AM[account.move]
            AML[account.move.line]
            AAL[account.analytic.line]
        end
        
        subgraph "Supporting"
            JNOTE[job.note]
            SUB[res.partner]
            EMP[hr.employee]
        end
    end

    subgraph "Reports & Views"
        REPORTS[Reports]
        VIEWS[Views]
        WIZARDS[Wizards]
    end

    %% Dependencies
    BASE --> JCS
    PROJECT --> JO
    PURCHASE --> PO
    STOCK --> MR
    TIMESHEET --> AAL
    ACCOUNT --> AM
    ANALYTIC --> JCS
    HR --> EMP
    MAIL --> JNOTE

    %% Core Relationships
    JCS --> JCL
    JO --> JCS
    JO --> MR
    JO --> BOQ
    
    %% Material Flow
    MR --> MRL
    MRL --> POL
    MR --> MP
    JO --> MC
    
    %% BOQ Flow
    BOQ --> BL
    BOQ --> BC
    BT --> BOQ
    BL --> JCL
    
    %% Integration Flow
    POL --> JCL
    AAL --> JCL
    AML --> JCL
    PO --> AM
    
    %% Supporting
    JNOTE --> JO
    SUB --> JO
    EMP --> MR
```

---

## Entity Relationship Diagram

```mermaid
erDiagram
    PROJECT ||--o{ JOB_COST_SHEET : has
    PROJECT ||--o{ JOB_ORDER : contains
    PROJECT ||--o{ BOQ : has
    PROJECT ||--o{ MATERIAL_REQUISITION : has
    PROJECT ||--o{ JOB_NOTE : contains
    
    JOB_ORDER ||--o{ JOB_COST_SHEET : has
    JOB_ORDER ||--o{ MATERIAL_REQUISITION : generates
    JOB_ORDER ||--o{ BOQ : contains
    JOB_ORDER ||--o{ MATERIAL_PLANNING : has
    JOB_ORDER ||--o{ MATERIAL_CONSUMPTION : tracks
    JOB_ORDER ||--o{ TIMESHEET : logs
    JOB_ORDER ||--o{ JOB_NOTE : documents
    
    JOB_COST_SHEET ||--o{ JOB_COST_LINE : contains
    JOB_COST_SHEET ||--|| ANALYTIC_ACCOUNT : tracks
    
    JOB_COST_LINE ||--o{ PURCHASE_ORDER_LINE : sources_from
    JOB_COST_LINE ||--o{ TIMESHEET : sources_from
    JOB_COST_LINE ||--o{ INVOICE_LINE : sources_from
    JOB_COST_LINE ||--o{ BOQ_LINE : linked_to
    
    BOQ ||--o{ BOQ_LINE : contains
    BOQ ||--o{ BOQ_CATEGORY : groups
    BOQ ||--o{ MATERIAL_REQUISITION : generates
    BOQ ||--o{ JOB_COST_LINE : creates
    
    BOQ_TEMPLATE ||--o{ BOQ_TEMPLATE_LINE : contains
    BOQ_TEMPLATE ||--o{ BOQ : instantiates
    
    MATERIAL_REQUISITION ||--o{ MATERIAL_REQUISITION_LINE : contains
    MATERIAL_REQUISITION ||--o{ PURCHASE_ORDER : creates
    MATERIAL_REQUISITION ||--o{ STOCK_PICKING : creates
    
    MATERIAL_REQUISITION_LINE ||--|| BOQ_LINE : references
    MATERIAL_REQUISITION_LINE ||--|| JOB_COST_LINE : references
    MATERIAL_REQUISITION_LINE ||--o{ PURCHASE_ORDER_LINE : creates
    
    PURCHASE_ORDER ||--o{ PURCHASE_ORDER_LINE : contains
    PURCHASE_ORDER ||--o{ INVOICE : generates
    
    PURCHASE_ORDER_LINE ||--|| JOB_COST_LINE : links_to
    PURCHASE_ORDER_LINE ||--|| MATERIAL_REQUISITION_LINE : from
    
    INVOICE ||--o{ INVOICE_LINE : contains
    INVOICE_LINE ||--|| JOB_COST_LINE : links_to
    INVOICE_LINE ||--|| PURCHASE_ORDER_LINE : from
    
    TIMESHEET ||--|| JOB_COST_LINE : links_to
    TIMESHEET ||--|| JOB_ORDER : assigned_to
    
    RES_PARTNER ||--o{ PROJECT : subcontractor_for
    RES_PARTNER ||--o{ PURCHASE_ORDER : vendor_for
    
    HR_EMPLOYEE ||--o{ TIMESHEET : logs
    HR_EMPLOYEE ||--o{ MATERIAL_REQUISITION : requests
    
    JOB_TYPE ||--o{ PROJECT : categorizes
    JOB_TYPE ||--o{ BOQ_TEMPLATE : categorizes
    
    JOB_STAGE ||--o{ JOB_ORDER : stages
    
    JOB_NOTE_TAG ||--o{ JOB_NOTE : tags
    JOB_NOTE ||--o{ JOB_NOTE : follows_up

    %% Entity Definitions with Key Fields
    PROJECT {
        int id PK
        string name
        boolean is_job_project
        float contract_amount
        date contract_date
        int job_type_id FK
    }
    
    JOB_ORDER {
        int id PK
        string name
        int project_id FK
        int stage_id FK
        int job_type_id FK
        string state
        float progress
        date date_start
        date date_end
        int user_id FK
    }
    
    JOB_COST_SHEET {
        int id PK
        string name
        int project_id FK
        int job_order_id FK
        int analytic_account_id FK
        string state
        float total_material_cost
        float total_labour_cost
        float total_overhead_cost
        float total_cost
        float actual_total_cost
    }
    
    JOB_COST_LINE {
        int id PK
        int cost_sheet_id FK
        string cost_type
        int product_id FK
        string name
        float planned_qty
        float actual_qty
        float unit_cost
        float actual_unit_cost
        float total_cost
        float actual_cost
        int source_po_line_id FK
        int source_timesheet_id FK
    }
    
    BOQ {
        int id PK
        string name
        int project_id FK
        int job_order_id FK
        int job_cost_sheet_id FK
        string state
        string title
        float total_cost
        float total_quantity
    }
    
    BOQ_LINE {
        int id PK
        int boq_id FK
        int product_id FK
        string description
        float quantity
        float unit_cost
        float total_cost
        float waste_percentage
        float contingency_percentage
        float adjusted_quantity
    }
    
    MATERIAL_REQUISITION {
        int id PK
        string name
        int project_id FK
        int job_order_id FK
        int job_cost_sheet_id FK
        string state
        date required_date
        string priority
    }
    
    MATERIAL_REQUISITION_LINE {
        int id PK
        int requisition_id FK
        int product_id FK
        float quantity
        float estimated_cost
        int boq_line_id FK
        int job_cost_line_id FK
        string requisition_action
    }
    
    PURCHASE_ORDER {
        int id PK
        string name
        int partner_id FK
        int material_requisition_id FK
        int job_cost_sheet_id FK
        int project_id FK
    }
    
    PURCHASE_ORDER_LINE {
        int id PK
        int order_id FK
        int product_id FK
        int material_requisition_line_id FK
        int job_cost_sheet_id FK
        int job_cost_line_id FK
    }
```

---

## Job Cost Sheet Data Flow

```mermaid
flowchart LR
    subgraph "Input Sources"
        PLAN[Planned Costs
        Manual Entry]
        PO[Purchase Orders
        Received Qty]
        TS[Timesheets
        Hours Logged]
        INV[Vendor Bills
        Actual Costs]
    end
    
    subgraph "Job Cost Sheet"
        JCS[job.cost.sheet]
        
        subgraph "Cost Lines"
            MAT[material_cost_ids
            Product Costs]
            LAB[labour_cost_ids
            Labor Costs]
            OH[overhead_cost_ids
            Overhead Costs]
        end
        
        subgraph "Computed Fields"
            TOT[total_cost
            total_material_cost
            total_labour_cost
            total_overhead_cost]
            ACT[actual_total_cost
            actual_material_cost
            actual_labour_cost
            actual_overhead_cost]
            VAR[variance calculations]
        end
    end
    
    subgraph "Output"
        REP[Reports]
        VIEW[Views]
        WIZ[Wizards]
    end
    
    %% Data Flow
    PLAN --> JCS
    
    JCS --> MAT
    JCS --> LAB
    JCS --> OH
    
    PO --> MAT
    PO --> OH
    TS --> LAB
    INV --> OH
    
    MAT --> TOT
    LAB --> TOT
    OH --> TOT
    
    MAT --> ACT
    LAB --> ACT
    OH --> ACT
    
    TOT --> VAR
    ACT --> VAR
    
    VAR --> REP
    VAR --> VIEW
    JCS --> WIZ
```

---

## Material Requisition Workflow

```mermaid
stateDiagram-v2
    [*] --> Draft: Create
    
    Draft --> Submitted: Submit
    Draft --> Cancelled: Cancel
    
    Submitted --> DeptApproved: Dept Manager Approve
    Submitted --> Rejected: Reject
    Submitted --> Cancelled: Cancel
    
    DeptApproved --> Approved: Manager Approve
    DeptApproved --> Rejected: Reject
    DeptApproved --> Cancelled: Cancel
    
    Approved --> Ordered: Create PO
    Approved --> Cancelled: Cancel
    
    Ordered --> Received: Goods Received
    Ordered --> Cancelled: Cancel
    
    Received --> [*]
    Rejected --> Draft: Reset
    Cancelled --> Draft: Reset
    
    note right of Draft
        User creates requisition
        Adds line items
        Links to project/job
    end note
    
    note right of Submitted
        Awaiting department
        manager approval
    end note
    
    note right of DeptApproved
        Awaiting requisition
        manager approval
    end note
    
    note right of Approved
        Ready to create
        Purchase Order
    end note
    
    note right of Ordered
        PO sent to vendor
        Awaiting delivery
    end note
    
    note right of Received
        Goods received
        Process complete
    end note
```

---

## BOQ to Cost Line Flow

```mermaid
sequenceDiagram
    actor User
    participant BOQ as boq.boq
    participant BL as boq.line
    participant JCS as job.cost.sheet
    participant JCL as job.cost.line
    
    User->>BOQ: Create BOQ from Template
    activate BOQ
    BOQ->>BL: Create BOQ Lines
    activate BL
    BL-->>BOQ: Lines Created
    deactivate BL
    BOQ-->>User: BOQ Ready
    deactivate BOQ
    
    User->>BOQ: action_create_job_cost_lines()
    activate BOQ
    
    loop For each BOQ Line with Product
        BOQ->>BL: Check for existing cost line
        activate BL
        BL-->>BOQ: Check result
        deactivate BL
        
        alt Cost Line Exists
            BOQ->>JCL: Link existing line to BOQ
        else Cost Line Missing
            BOQ->>JCS: Get/Create Job Cost Sheet
            activate JCS
            JCS-->>BOQ: Sheet Reference
            deactivate JCS
            
            BOQ->>JCL: Create Job Cost Line
            activate JCL
            JCL->>JCL: Set cost_type='material'
            JCL->>JCL: Set planned_qty=BOQ qty
            JCL->>JCL: Set unit_cost=BOQ cost
            JCL->>JCL: Link boq_line_id
            JCL-->>BOQ: Line Created
            deactivate JCL
        end
    end
    
    BOQ-->>User: Return action view cost lines
    deactivate BOQ
```

---

## Purchase Order Integration

```mermaid
flowchart TD
    subgraph "Purchase Order Creation"
        MR[Material Requisition]
        WIZ_RFQ[Create RFQ Wizard]
        PO_CREATE[Create PO]
    end
    
    subgraph "PO Line Processing"
        POL[Purchase Order Line]
        
        subgraph "Auto-Link Logic"
            CHECK_DUP{Check for
            Duplicate}
            FIND_JCS[Find Job Cost Sheet
            from Context]
            FIND_JCL[Find/Create
            Job Cost Line]
            LINK[Link POL to JCL]
        end
    end
    
    subgraph "Receipt & Cost Update"
        RECEIVE[Receive Products]
        UPDATE_ACT[Update Actual Costs
            in Job Cost Line]
        RECOMPUTE[Recompute
            Sheet Totals]
    end
    
    %% Flow
    MR --> WIZ_RFQ
    WIZ_RFQ --> PO_CREATE
    
    PO_CREATE --> POL
    
    POL --> CHECK_DUP
    CHECK_DUP -->|Duplicate Found| LINK
    CHECK_DUP -->|No Duplicate| FIND_JCS
    FIND_JCS --> FIND_JCL
    FIND_JCL --> LINK
    
    LINK --> RECEIVE
    RECEIVE --> UPDATE_ACT
    UPDATE_ACT --> RECOMPUTE
    
    style CHECK_DUP fill:#ff9,stroke:#333
    style UPDATE_ACT fill:#9f9,stroke:#333
```

---

## Timesheet Integration

```mermaid
sequenceDiagram
    participant TS as account.analytic.line
    participant AUTO as Auto-Link Method
    participant JCS as job.cost.sheet
    participant JCL as job.cost.line
    
    %% Timesheet Creation
    Note over TS: User creates timesheet
    TS->>AUTO: create() called
    activate AUTO
    
    AUTO->>JCS: Search by analytic_account_id
    activate JCS
    JCS-->>AUTO: Return matching sheet
    deactivate JCS
    
    alt Single Labour Line
        AUTO->>JCL: Auto-link to single line
        activate JCL
        JCL-->>AUTO: Linked
        deactivate JCL
    else Multiple Labour Lines
        AUTO->>AUTO: Try match by task/job order
        alt Match Found
            AUTO->>JCL: Link to matching line
        else No Match
            AUTO->>AUTO: Leave unlinked
        end
    end
    
    AUTO-->>TS: Return
    deactivate AUTO
    
    %% Cost Calculation
    Note over TS: Timesheet amount is negative
    TS->>JCL: _compute_actual_costs()
    activate JCL
    JCL->>JCL: Use abs() for display
    JCL->>JCL: Sum unit_amount to qty
    JCL-->>TS: Actual cost computed
    deactivate JCL
```

---

## Invoice Integration

```mermaid
flowchart LR
    subgraph "Invoice Creation"
        PO[Purchase Order]
        INV[Vendor Bill
        account.move]
        INV_LINE[Invoice Line
        account.move.line]
    end
    
    subgraph "Linking Logic"
        ORIGIN{Has Origin
        from PO?}
        GET_PO[Get PO
        from origin]
        GET_JCS[Get Job Cost Sheet
        from PO]
        LINK_INV[Link Invoice
        to Job Cost Sheet]
    end
    
    subgraph "Line Processing"
        CHECK_POL{Has PO Line?}
        GET_JCL[Get Job Cost Line
        from PO Line]
        CHECK_ANALYTIC{Has Analytic?}
        FIND_BY_ANALYTIC[Find JCS by
        Analytic Account]
        LINK_LINE[Link Invoice Line
        to Job Cost Line]
    end
    
    %% Flow
    PO --> INV
    
    INV --> ORIGIN
    ORIGIN -->|Yes| GET_PO
    GET_PO --> GET_JCS
    GET_JCS --> LINK_INV
    
    INV --> INV_LINE
    INV_LINE --> CHECK_POL
    CHECK_POL -->|Yes| GET_JCL
    CHECK_POL -->|No| CHECK_ANALYTIC
    GET_JCL --> LINK_LINE
    
    CHECK_ANALYTIC -->|Yes| FIND_BY_ANALYTIC
    FIND_BY_ANALYTIC --> LINK_LINE
    CHECK_ANALYTIC -->|No| NO_LINK[No Link]
    
    style ORIGIN fill:#ff9,stroke:#333
    style CHECK_POL fill:#ff9,stroke:#333
    style LINK_INV fill:#9f9,stroke:#333
    style LINK_LINE fill:#9f9,stroke:#333
```

---

## Class Diagram

```mermaid
classDiagram
    class JobCostSheet {
        +Char name
        +Many2one project_id
        +Many2one job_order_id
        +Many2one analytic_account_id
        +Selection state
        +One2many material_cost_ids
        +One2many labour_cost_ids
        +One2many overhead_cost_ids
        +Float total_material_cost
        +Float total_labour_cost
        +Float total_overhead_cost
        +Float total_cost
        +Float actual_material_cost
        +Float actual_labour_cost
        +Float actual_overhead_cost
        +Float actual_total_cost
        +Float material_variance
        +Float labour_variance
        +Float overhead_variance
        +Float total_variance
        +Int purchase_order_count
        +Int timesheet_count
        +Int invoice_count
        
        +action_approve()
        +action_done()
        +action_cancel()
        +action_sync_actual_costs()
        +action_create_rfq()
        +action_view_purchase_orders()
        +action_view_timesheets()
        +action_view_invoices()
        +_compute_totals()
        +_compute_actual_costs()
        +_compute_variance()
    }
    
    class JobCostLine {
        +Many2one cost_sheet_id
        +Selection cost_type
        +Many2one product_id
        +Char name
        +Float planned_qty
        +Float actual_qty
        +Float unit_cost
        +Float actual_unit_cost
        +Float total_cost
        +Float actual_cost
        +Float qty_variance
        +Float cost_variance
        +Many2one uom_id
        +Many2one boq_line_id
        +Many2one source_po_line_id
        +Many2one source_timesheet_id
        +Many2one source_invoice_line_id
        
        +_compute_total_cost()
        +_compute_actual_qty()
        +_compute_actual_unit_cost()
        +_compute_actual_cost()
        +_compute_variance()
        +update_actual_costs_from_purchases()
        +get_or_create_cost_line()
    }
    
    class JobOrder {
        +Char name
        +Many2one project_id
        +Many2one task_id
        +Many2one stage_id
        +Selection state
        +Float progress
        +Date date_start
        +Date date_end
        +Many2one user_id
        +One2many job_cost_sheet_ids
        +One2many material_requisition_ids
        +One2many timesheet_ids
        +One2many boq_ids
        
        +action_start()
        +action_done()
        +action_cancel()
        +action_view_cost_sheets()
        +action_view_timesheets()
        +action_view_material_requisitions()
        +_compute_costs()
        +_compute_counts()
    }
    
    class MaterialRequisition {
        +Char name
        +Many2one project_id
        +Many2one job_order_id
        +Many2one job_cost_sheet_id
        +Many2one boq_id
        +Selection state
        +Date required_date
        +Selection priority
        +One2many line_ids
        +Float total_cost
        
        +action_submit()
        +action_dept_approve()
        +action_approve()
        +action_reject()
        +action_create_purchase_order()
        +action_create_picking()
        +_compute_total_amount()
    }
    
    class BOQ {
        +Char name
        +Many2one project_id
        +Many2one job_order_id
        +Many2one job_cost_sheet_id
        +Selection state
        +Char title
        +One2many line_ids
        +One2many category_ids
        +Float total_quantity
        +Float total_cost
        +Float total_requisitioned_amount
        +Float overall_purchase_progress
        
        +action_approve()
        +action_lock()
        +action_create_material_requisition()
        +action_create_job_cost_lines()
        +_compute_totals()
        +_compute_purchase_totals()
    }
    
    class BOQLine {
        +Many2one boq_id
        +Many2one product_id
        +Text description
        +Float quantity
        +Float unit_cost
        +Float total_cost
        +Float waste_percentage
        +Float contingency_percentage
        +Float adjusted_quantity
        +Float adjusted_total_cost
        +Float total_requisitioned_qty
        +Float total_ordered_qty
        +Float total_received_qty
        +Float remaining_qty
        +Selection status
        
        +_compute_total_cost()
        +_compute_adjusted_values()
        +_compute_purchase_tracking()
        +_compute_status()
    }
    
    class PurchaseOrder {
        +Many2one material_requisition_id
        +Many2one job_cost_sheet_id
        +Many2one project_id
        +Many2one job_order_id
        
        +button_confirm()
        +_update_job_cost_sheet_actual_costs()
    }
    
    class PurchaseOrderLine {
        +Many2one material_requisition_line_id
        +Many2one job_cost_sheet_id
        +Many2one job_cost_line_id
        +Many2one analytic_account_id
        
        +_onchange_job_cost_sheet_id()
        +_onchange_job_cost_line_id()
        +_onchange_analytic_account_id()
    }
    
    class AccountMove {
        +Many2one job_cost_sheet_id
        +Many2one project_id
        +Many2one job_order_id
    }
    
    class AccountMoveLine {
        +Many2one job_cost_line_id
        
        +_onchange_analytic_distribution()
    }
    
    class AccountAnalyticLine {
        +Many2one job_cost_line_id
        +Many2one job_order_id
        
        +_auto_link_to_job_cost_line()
        +action_create_job_cost_line()
    }
    
    %% Relationships
    JobCostSheet "1" --> "*" JobCostLine : contains
    JobCostSheet "1" --> "*" MaterialRequisition : linked
    JobOrder "1" --> "*" JobCostSheet : has
    JobOrder "1" --> "*" MaterialRequisition : generates
    JobOrder "1" --> "*" BOQ : contains
    MaterialRequisition "1" --> "*" PurchaseOrder : creates
    PurchaseOrder "1" --> "*" PurchaseOrderLine : contains
    PurchaseOrder "1" --> "1" AccountMove : generates
    BOQ "1" --> "*" BOQLine : contains
    BOQ "1" --> "*" JobCostLine : creates
    JobCostLine "1" --> "*" PurchaseOrderLine : sources
    JobCostLine "1" --> "*" AccountAnalyticLine : sources
    JobCostLine "1" --> "*" AccountMoveLine : sources
```

---

## Security Model

```mermaid
flowchart TD
    subgraph "User Groups"
        BASE[base.group_user]
        PU[project.group_project_user]
        PM[project.group_project_manager]
        JCU[group_job_costing_user]
        JCM[group_job_costing_manager]
        MRU[group_material_requisition_user]
        MRM[group_material_requisition_manager]
        DM[group_department_manager]
    end
    
    subgraph "Record Access Rules"
        JCS_USER[Job Cost Sheet
        User Rule:
        creator OR project user]
        JCS_MGR[Job Cost Sheet
        Manager Rule:
        All Records]
        
        JO_USER[Job Order
        User Rule:
        assigned OR project user]
        JO_MGR[Job Order
        Manager Rule:
        All Records]
        
        MR_USER[Material Requisition
        User Rule:
        own employee]
        MR_DM[Material Requisition
        Dept Rule:
        dept manager]
        MR_MGR[Material Requisition
        Manager Rule:
        All Records]
        
        JN_USER[Job Note
        User Rule:
        creator OR assigned]
        JN_MGR[Job Note
        Manager Rule:
        All Records]
        
        MC_ALL[Multi-Company
        All Models:
        company_id in user.companies]
    end
    
    %% Group Hierarchy
    BASE --> PU
    PU --> JCU
    JCU --> JCM
    PM --> JCM
    
    MRU --> MRM
    
    %% Rule Assignment
    JCU --> JCS_USER
    JCM --> JCS_MGR
    JCU --> JO_USER
    JCM --> JO_MGR
    MRU --> MR_USER
    DM --> MR_DM
    MRM --> MR_MGR
    JCU --> JN_USER
    JCM --> JN_MGR
    
    %% Multi-Company applies to all
    BASE --> MC_ALL
    
    style JCM fill:#9f9,stroke:#333
    style MRM fill:#9f9,stroke:#333
    style JCS_MGR fill:#9f9,stroke:#333
    style JO_MGR fill:#9f9,stroke:#333
    style MR_MGR fill:#9f9,stroke:#333
    style JN_MGR fill:#9f9,stroke:#333
```

---

## Data Synchronization Flow

```mermaid
sequenceDiagram
    participant User
    participant PO as Purchase Order
    participant POL as PO Line
    participant JCL as Job Cost Line
    participant JCS as Job Cost Sheet
    participant TS as Timesheet
    participant INV as Vendor Bill
    
    %% PO Creation Flow
    User->>PO: Create PO with Job Cost Sheet
    activate PO
    PO->>POL: Create Lines
    activate POL
    POL->>JCL: Auto-create/Link Cost Line
    activate JCL
    JCL-->>POL: Linked
    deactivate JCL
    POL-->>PO: Lines Created
    deactivate POL
    PO-->>User: PO Created
    deactivate PO
    
    %% Receipt Flow
    User->>PO: Confirm Receipt
    activate PO
    PO->>POL: Update qty_received
    activate POL
    POL->>JCL: Trigger cost update
    activate JCL
    JCL->>JCL: Update actual_qty
    JCL->>JCL: Update actual_cost
    JCL->>JCS: Trigger recompute
    activate JCS
    JCS->>JCS: _compute_actual_costs()
    JCS-->>JCL: Complete
    deactivate JCS
    JCL-->>POL: Complete
    deactivate JCL
    POL-->>PO: Complete
    deactivate POL
    PO-->>User: Receipt Complete
    deactivate PO
    
    %% Timesheet Flow
    User->>TS: Log Hours
    activate TS
    TS->>JCL: Auto-link/Create Cost Line
    activate JCL
    JCL->>JCL: Update from timesheet
    JCL->>JCS: Trigger recompute
    activate JCS
    JCS-->>JCL: Complete
    deactivate JCS
    JCL-->>TS: Linked
    deactivate JCL
    TS-->>User: Timesheet Saved
    deactivate TS
    
    %% Invoice Flow
    PO->>INV: Generate Bill
    activate INV
    INV->>JCS: Link to Cost Sheet
    INV->>JCL: Link Lines to Cost Lines
    activate JCL
    JCL->>JCS: Trigger recompute
    activate JCS
    JCS-->>JCL: Complete
    deactivate JCS
    JCL-->>INV: Linked
    deactivate JCL
    INV-->>PO: Complete
    deactivate INV
```

---

## Summary

These diagrams illustrate:

1. **Modular Architecture** - Clear separation of concerns between core costing, material management, BOQ, and integration components

2. **Complex Relationships** - Many-to-many relationships between projects, job orders, cost sheets, and external documents

3. **Automated Data Flow** - Purchase orders, timesheets, and invoices automatically update cost line actual costs

4. **Multi-Level Security** - Hierarchical access control with user, department manager, and global manager levels

5. **State-Driven Workflows** - Material requisitions follow a defined approval workflow with multiple checkpoints

6. **Duplicate Prevention** - Source tracking fields prevent duplicate cost line creation

7. **Variance Tracking** - Real-time comparison between planned and actual costs with automatic recomputation
