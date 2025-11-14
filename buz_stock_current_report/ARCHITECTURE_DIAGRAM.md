# Architecture Diagram: Enhanced Warehouse Sidebar with Transit Locations

## Data Flow

```mermaid
graph TD
    A[User Opens Current Stock View] --> B[WarehouseSidebar Component Loads]
    B --> C[JavaScript Calls get_warehouses_with_locations]
    C --> D[Python Model Executes SQL Queries]
    D --> E[Returns Warehouse Data Structure]
    E --> F[JavaScript Processes Data]
    F --> G[XML Template Renders Sidebar]
    G --> H[User Sees Internal & Transit Locations]
    
    D --> D1[Query 1: Warehouse Summary]
    D --> D2[Query 2: Internal Locations]
    D --> D3[Query 3: Transit Locations]
    
    E --> E1[Warehouse Object]
    E1 --> E2[internal_locations Array]
    E1 --> E3[transit_locations Array]
    
    G --> G1[Render Warehouse Header]
    G1 --> G2[Render Internal Locations Section]
    G2 --> G3[Render Transit Locations Section]
```

## Component Structure

```mermaid
classDiagram
    class StockCurrentReport {
        +get_warehouses_with_locations()
        -SQL queries for warehouses
        -SQL queries for internal locations
        -SQL queries for transit locations
    }
    
    class WarehouseSidebar {
        -state: warehouses
        -state: expandedWarehouses
        +loadWarehouses()
        +toggleWarehouse()
        +onWarehouseClick()
        +onLocationClick()
        +getLocationTypeIcon()
    }
    
    class WarehouseSidebarTemplate {
        +renderWarehouseHeader()
        +renderInternalLocations()
        +renderTransitLocations()
        +renderLocationItem()
    }
    
    StockCurrentReport --> WarehouseSidebar : provides data
    WarehouseSidebar --> WarehouseSidebarTemplate : renders UI
```

## Data Structure

```mermaid
erDiagram
    WAREHOUSE {
        int id
        string name
        string code
        int location_count
        int total_products
        float total_value
        internal_locations[]
        transit_locations[]
    }
    
    INTERNAL_LOCATION {
        int id
        string name
        string complete_name
        string usage
        int product_count
        float total_quantity
        float total_value
    }
    
    TRANSIT_LOCATION {
        int id
        string name
        string complete_name
        string usage
        int product_count
        float total_quantity
        float total_value
    }
    
    WAREHOUSE ||--o{ INTERNAL_LOCATION : contains
    WAREHOUSE ||--o{ TRANSIT_LOCATION : contains
```

## UI Layout

```mermaid
graph TB
    subgraph Warehouse Sidebar
        WH[Warehouse Header]
        WH --> IL[Internal Locations Section]
        WH --> TL[Transit Locations Section]
        
        subgraph Internal Locations
            IL1[Location 1]
            IL2[Location 2]
            IL3[...]
        end
        
        subgraph Transit Locations
            TL1[Transit Location 1]
            TL2[Transit Location 2]
            TL3[...]
        end
    end
    
    subgraph Main Content
        R[Stock Report Table/Kanban]
    end
    
    IL1 --> R
    IL2 --> R
    TL1 --> R
    TL2 --> R