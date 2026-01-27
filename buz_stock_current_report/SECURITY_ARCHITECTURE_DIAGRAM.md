# Security Architecture Diagram

## User Group Hierarchy

```mermaid
graph TD
    A[Administrator] --> B[Stock Manager]
    A --> C[Stock User]
    A --> D[Stock Cost Viewer]
    
    B --> E[Can View Cost Fields]
    C --> F[Cannot View Cost Fields]
    D --> E
    
    E --> G[Tree View with Cost]
    E --> H[Form View with Cost]
    E --> I[Kanban View with Cost]
    E --> J[Excel Export with Cost]
    
    F --> K[Tree View without Cost]
    F --> L[Form View without Cost]
    F --> M[Kanban View without Cost]
    F --> N[Excel Export without Cost]
```

## Implementation Flow

```mermaid
flowchart LR
    A[User Login] --> B{Check User Groups}
    B -->|Has Cost Viewer Group| C[Show Cost Fields]
    B -->|No Cost Viewer Group| D[Hide Cost Fields]
    
    C --> E[Display Unit Cost]
    C --> F[Display Total Value]
    C --> G[Include Cost in Excel]
    
    D --> H[Hide Unit Cost]
    D --> I[Hide Total Value]
    D --> J[Exclude Cost from Excel]
```

## Field Visibility Matrix

| View/Component | Regular User | Cost Viewer | Stock Manager |
|----------------|--------------|-------------|---------------|
| Tree View - Unit Cost | ❌ Hidden | ✅ Visible | ✅ Visible |
| Tree View - Total Value | ❌ Hidden | ✅ Visible | ✅ Visible |
| Form View - Unit Cost | ❌ Hidden | ✅ Visible | ✅ Visible |
| Form View - Total Value | ❌ Hidden | ✅ Visible | ✅ Visible |
| Kanban View - Unit Cost | ❌ Hidden | ✅ Visible | ✅ Visible |
| Kanban View - Total Value | ❌ Hidden | ✅ Visible | ✅ Visible |
| Excel Export - Cost Columns | ❌ Hidden | ✅ Visible | ✅ Visible |
| Search Filter - High Value | ❌ Hidden | ✅ Visible | ✅ Visible |

## Security Implementation Layers

```mermaid
graph TB
    A[Security Layer] --> B[Group-Based Access Control]
    A --> C[Field-Level Security]
    A --> D[View-Level Security]
    A --> E[Export-Level Security]
    
    B --> F[group_stock_cost_viewer]
    
    C --> G[unit_cost groups parameter]
    C --> H[total_value groups parameter]
    
    D --> I[Tree View groups attribute]
    D --> J[Form View groups attribute]
    D --> K[Kanban View groups attribute]
    
    E --> L[Excel Export Permission Check]
    E --> M[Wizard SQL Conditional Logic]