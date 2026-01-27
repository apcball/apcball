# Warranty Management Workflow Diagram

## Current Workflow (Automatic)
```mermaid
flowchart TD
    A[Product Configuration] --> B[Auto Warranty Enabled?]
    B -->|Yes| C[Create Sale Order]
    B -->|No| D[No Warranty]
    C --> E[Confirm & Deliver Order]
    E --> F[Stock Picking Validated]
    F --> G[Auto Create Warranty Card]
    G --> H[Warranty Card Active]
    H --> I[Customer Can Make Claims]
```

## New Workflow (Manual)
```mermaid
flowchart TD
    A[Product Configuration] --> B[Set Warranty Duration]
    B --> C[Create Sale Order]
    C --> D[Confirm & Deliver Order]
    D --> E[Stock Picking Validated]
    E --> F[Order Delivered]
    F --> G[User Clicks 'Create Warranty Card']
    G --> H[Check Products with Warranty]
    H --> I[Create Warranty Cards]
    I --> J[Warranty Cards Active]
    J --> K[Customer Can Make Claims]
    
    style G fill:#e1f5fe
    style H fill:#f3e5f5
    style I fill:#e8f5e9
```

## Key Changes
1. **Removed**: Automatic warranty card creation on delivery
2. **Added**: Manual "Create Warranty Card" button on Sale Order
3. **Modified**: Product form to always show warranty duration (no auto checkbox)
4. **Preserved**: All warranty claim and RMA workflows

## Implementation Flow
```mermaid
sequenceDiagram
    participant User
    participant SO as Sale Order
    participant WC as Warranty Card
    participant SP as Stock Picking
    
    User->>SO: Create & Confirm Order
    SO->>SP: Create Delivery
    SP->>SP: Validate Delivery
    User->>SO: Click 'Create Warranty Card'
    SO->>SO: Check Delivered Products
    SO->>WC: Create Warranty Cards
    WC->>User: Show Created Cards