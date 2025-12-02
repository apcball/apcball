# Employee Purchase Requisition - Total Amount Implementation

## System Architecture

```mermaid
erDiagram
    employee.purchase.requisition ||--o{ requisition.order : contains
    
    employee.purchase.requisition {
        string name
        many2one employee_id
        many2one dept_id
        date requisition_date
        float total_amount
        one2many requisition_order_ids
    }
    
    requisition.order {
        many2one requisition_product_id
        many2one product_id
        float quantity
        float unit_price
        float price_subtotal
        many2one partner_id
    }
```

## Implementation Flow

```mermaid
flowchart TD
    A[User adds/changes line item] --> B[Update quantity or unit_price]
    B --> C[Compute price_subtotal = quantity × unit_price]
    C --> D[Trigger total_amount recomputation]
    D --> E[Compute total_amount = sum of all price_subtotal]
    E --> F[Display updated totals in views]
    
    G[Form View] --> H[Show total_amount field]
    I[Tree View] --> J[Show total_amount column]
    K[Kanban View] --> L[Show total_amount in card]
    M[Line Items Tree] --> N[Show price_subtotal column]
```

## View Modifications

### Form View Changes
```mermaid
graph LR
    A[Existing Form] --> B[Add Total Amount Field]
    B --> C[Position in button_box area]
    C --> D[Display as stat button]
```

### Tree View Changes
```mermaid
graph LR
    A[Existing Tree Columns] --> B[Add Total Amount Column]
    B --> C[Format as currency]
    C --> D[Position after state column]
```

### Kanban View Changes
```mermaid
graph LR
    A[Existing Kanban Card] --> B[Add Total Amount Display]
    B --> C[Show in card content area]
```

## Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Form View
    participant M as Main Model
    participant L as Line Model
    participant V as Views
    
    U->>F: Edit line item
    F->>L: Update quantity/price
    L->>L: Compute price_subtotal
    L->>M: Trigger onchange
    M->>M: Compute total_amount
    M->>V: Update all views
    V->>U: Display new totals