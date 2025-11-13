# Architecture Diagram: Easy Pick Product Transfer Feature

## System Architecture Overview

```mermaid
graph TB
    subgraph "UI Layer"
        A[Kanban View] --> B[Product Selection]
        C[List View] --> B
        B --> D[Transfer Button]
        D --> E[Transfer Wizard]
    end
    
    subgraph "Controller Layer"
        F[StockKanbanController] --> A
        G[StockListController] --> C
        H[SelectionManager] --> B
        I[TransferWizardController] --> E
    end
    
    subgraph "Model Layer"
        J[StockCurrentReport] --> F
        J --> G
        K[StockCurrentTransferWizard] --> I
        L[StockCurrentTransferWizardLine] --> K
    end
    
    subgraph "Core Odoo Models"
        M[StockPicking] --> K
        N[StockMove] --> M
        O[StockLocation] --> K
        P[ProductProduct] --> L
        Q[UoM] --> L
    end
    
    subgraph "Security Layer"
        R[Access Rights] --> K
        R --> L
        S[Group Permissions] --> R
    end
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant KanbanView
    participant SelectionManager
    participant TransferWizard
    participant StockPicking
    participant StockMove
    
    User->>KanbanView: Select products
    KanbanView->>SelectionManager: Track selections
    User->>KanbanView: Click Transfer button
    KanbanView->>SelectionManager: Get selected products
    SelectionManager->>TransferWizard: Open with selected data
    TransferWizard->>User: Show transfer form
    User->>TransferWizard: Configure transfer
    TransferWizard->>TransferWizard: Validate quantities
    TransferWizard->>StockPicking: Create picking
    StockPicking->>StockMove: Create moves
    StockMove->>StockMove: Validate transfer
    StockMove->>User: Show transfer result
```

## Component Interaction Diagram

```mermaid
graph LR
    subgraph "Frontend Components"
        A[Kanban Cards]
        B[List Rows]
        C[Selection Checkboxes]
        D[Transfer Button]
        E[Wizard Form]
    end
    
    subgraph "JavaScript Controllers"
        F[Selection Manager]
        G[View Controllers]
        H[Wizard Controller]
    end
    
    subgraph "Backend Models"
        I[Stock Current Report]
        J[Transfer Wizard]
        K[Transfer Wizard Lines]
    end
    
    subgraph "Core Stock Models"
        L[Stock Picking]
        M[Stock Move]
        N[Stock Quant]
    end
    
    A --> C
    B --> C
    C --> F
    F --> D
    D --> H
    H --> J
    J --> K
    J --> L
    L --> M
    M --> N
    I --> A
    I --> B
    G --> A
    G --> B
```

## Class Diagram

```mermaid
classDiagram
    class StockCurrentReport {
        +product_id: Many2one
        +location_id: Many2one
        +quantity: Float
        +action_view_product_moves()
        +action_open_transfer_wizard()
    }
    
    class StockCurrentTransferWizard {
        +source_location_id: Many2one
        +destination_location_id: Many2one
        +picking_type_id: Many2one
        +immediate_transfer: Boolean
        +line_ids: One2many
        +action_create_transfer()
        +_get_picking_type()
    }
    
    class StockCurrentTransferWizardLine {
        +wizard_id: Many2one
        +product_id: Many2one
        +source_location_id: Many2one
        +available_quantity: Float
        +quantity_to_transfer: Float
        +uom_id: Many2one
        +_check_quantity()
        +_onchange_product_location()
    }
    
    class SelectionManager {
        +selectedProducts: Map
        +toggleProductSelection()
        +openTransferWizard()
        +clearSelection()
    }
    
    class StockKanbanWithTransferController {
        +selectionManager: SelectionManager
        +setup()
        +renderSelection()
    }
    
    StockCurrentReport --> StockKanbanWithTransferController
    StockKanbanWithTransferController --> SelectionManager
    SelectionManager --> StockCurrentTransferWizard
    StockCurrentTransferWizard --> StockCurrentTransferWizardLine
```

## State Management Diagram

```mermaid
stateDiagram-v2
    [*] --> ProductSelection
    ProductSelection --> SelectingProducts: User selects products
    SelectingProducts --> ProductsSelected: User clicks transfer
    ProductsSelected --> WizardOpen: Open transfer wizard
    WizardOpen --> ConfiguringTransfer: User configures transfer
    ConfiguringTransfer --> ValidatingData: User submits
    ValidatingData --> ValidationFailed: Invalid data
    ValidationFailed --> ConfiguringTransfer: Fix errors
    ValidatingData --> CreatingTransfer: Valid data
    CreatingTransfer --> TransferCreated: Success
    CreatingTransfer --> TransferError: System error
    TransferError --> ConfiguringTransfer: Retry
    TransferCreated --> [*]: Complete
```

## Database Schema Diagram

```mermaid
erDiagram
    stock_current_report {
        int id PK
        int product_id FK
        int location_id FK
        float quantity
        float free_to_use
        float incoming
        float outgoing
    }
    
    stock_current_transfer_wizard {
        int id PK
        int source_location_id FK
        int destination_location_id FK
        int picking_type_id FK
        boolean immediate_transfer
        datetime scheduled_date
        text notes
    }
    
    stock_current_transfer_wizard_line {
        int id PK
        int wizard_id FK
        int product_id FK
        int source_location_id FK
        float available_quantity
        float quantity_to_transfer
        int uom_id FK
    }
    
    stock_picking {
        int id PK
        int picking_type_id FK
        int location_id FK
        int location_dest_id FK
        string state
    }
    
    stock_move {
        int id PK
        int picking_id FK
        int product_id FK
        int location_id FK
        int location_dest_id FK
        float product_uom_qty
        float quantity_done
    }
    
    stock_current_report ||--o{ stock_current_transfer_wizard_line : "provides data"
    stock_current_transfer_wizard ||--o{ stock_current_transfer_wizard_line : "has lines"
    stock_current_transfer_wizard ||--|| stock_picking : "creates"
    stock_picking ||--o{ stock_move : "contains"
}
```

## Security Architecture

```mermaid
graph TB
    subgraph "User Groups"
        A[Stock User]
        B[Stock Manager]
        C[Stock Cost Viewer]
    end
    
    subgraph "Access Rights"
        D[Read Access]
        E[Write Access]
        F[Create Access]
        G[Delete Access]
    end
    
    subgraph "Model Permissions"
        H[Stock Current Report]
        I[Transfer Wizard]
        J[Transfer Wizard Lines]
        K[Stock Picking]
        L[Stock Move]
    end
    
    A --> D
    A --> F
    A --> G
    A --> H
    A --> I
    A --> J
    
    B --> D
    B --> E
    B --> F
    B --> G
    B --> H
    B --> I
    B --> J
    B --> K
    B --> L
    
    C --> D
    C --> H
    
    D --> H
    F --> I
    F --> J
    E --> K
    E --> L
```

## Performance Optimization Strategy

```mermaid
graph LR
    subgraph "Frontend Optimization"
        A[Lazy Loading]
        B[Selection Caching]
        C[DOM Optimization]
    end
    
    subgraph "Backend Optimization"
        D[Batch Processing]
        E[Query Optimization]
        F[Connection Pooling]
    end
    
    subgraph "Database Optimization"
        G[Indexing Strategy]
        H[Query Planning]
        I[Transaction Management]
    end
    
    A --> D
    B --> E
    C --> F
    D --> G
    E --> H
    F --> I
```

## Error Handling Flow

```mermaid
flowchart TD
    A[User Action] --> B{Validation Check}
    B -->|Valid| C[Execute Action]
    B -->|Invalid| D[Show Error Message]
    D --> A
    C --> E{System Response}
    E -->|Success| F[Show Success Message]
    E -->|Error| G[Log Error]
    G --> H[Show User-Friendly Error]
    H --> A
    F --> I[Update UI State]