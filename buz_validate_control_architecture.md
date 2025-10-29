# BUZ Validate Control Module - Architecture Diagram

## Module Architecture Overview

```mermaid
graph TB
    subgraph "BUZ Validate Control Module"
        A[__manifest__.py] --> B[models/]
        A --> C[views/]
        A --> D[security/]
        A --> E[static/]
        
        B --> F[stock_picking.py]
        B --> G[account_move.py]
        
        C --> H[stock_picking_views.xml]
        C --> I[account_move_views.xml]
        
        D --> J[security.xml]
        D --> K[ir.model.access.csv]
        
        E --> L[description/icon.png]
    end
    
    subgraph "Odoo Core Models"
        M[stock.picking]
        N[account.move]
        O[res.groups]
    end
    
    subgraph "Security Layer"
        P[group_validate_privileged]
        Q[UI Button Visibility]
        R[Server-side Validation]
    end
    
    F --> M
    G --> N
    J --> O
    J --> P
    
    H --> Q
    I --> Q
    
    F --> R
    G --> R
    
    P --> Q
    P --> R
```

## User Workflow

```mermaid
flowchart TD
    A[User attempts to Validate/Post] --> B{User in Validate Privileged group?}
    
    B -->|Yes| C[Button visible in UI]
    B -->|No| D[Button hidden in UI]
    
    C --> E[User clicks button]
    D --> F[Cannot access button]
    
    E --> G{Server-side permission check}
    G -->|Pass| H[Action executed successfully]
    G -->|Fail| I[AccessError raised]
    
    F --> J[User cannot proceed]
    I --> K[Error message displayed]
    H --> L[Document validated/posted]
```

## Security Implementation Flow

```mermaid
sequenceDiagram
    participant U as User
    participant UI as UI Layer
    participant S as Server
    participant DB as Database
    
    U->>UI: Opens document form
    UI->>DB: Check user groups
    DB-->>UI: Return user groups
    UI->>UI: Show/hide buttons based on groups
    
    alt User has privileges
        UI->>U: Show Validate/Post buttons
        U->>UI: Click Validate/Post button
        UI->>S: Call button_validate()/action_post()
        S->>S: Check has_group() again
        S->>DB: Execute action
        DB-->>S: Success
        S-->>UI: Success response
        UI-->>U: Document validated/posted
    else User doesn't have privileges
        UI->>U: Hide Validate/Post buttons
        Note over U,S: If somehow bypassed
        U->>S: Direct method call
        S->>S: Check has_group()
        S-->>U: Raise AccessError
    end
```

## File Dependencies

```mermaid
graph LR
    subgraph "Core Dependencies"
        A[stock] --> D[stock.picking]
        B[account] --> E[account.move]
        C[base] --> F[res.groups]
    end
    
    subgraph "Module Files"
        G[__manifest__.py] --> H[models/stock_picking.py]
        G --> I[models/account_move.py]
        G --> J[views/stock_picking_views.xml]
        G --> K[views/account_move_views.xml]
        G --> L[security/security.xml]
    end
    
    H --> D
    I --> E
    J --> D
    K --> E
    L --> F