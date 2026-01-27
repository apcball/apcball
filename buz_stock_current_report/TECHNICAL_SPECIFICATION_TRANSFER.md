# Technical Specification: Easy Pick Product Transfer Feature

## 1. Model Specifications

### 1.1 Stock Current Transfer Wizard Model

```python
class StockCurrentTransferWizard(models.TransientModel):
    _name = 'stock.current.transfer.wizard'
    _description = 'Stock Current Transfer Wizard'
    
    # Fields
    source_location_id = fields.Many2one('stock.location', string='Source Location')
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', 
                                           required=True, domain="[('usage', '=', 'internal')]")
    picking_type_id = fields.Many2one('stock.picking.type', string='Operation Type')
    immediate_transfer = fields.Boolean(string='Immediate Transfer', default=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', default=fields.Datetime.now)
    notes = fields.Text(string='Notes')
    line_ids = fields.One2many('stock.current.transfer.wizard.line', 'wizard_id', string='Products')
    
    # Methods
    def action_create_transfer(self):
        """Create stock transfer from wizard data"""
        
    def _get_picking_type(self):
        """Get appropriate picking type for internal transfer"""
```

### 1.2 Stock Current Transfer Wizard Line Model

```python
class StockCurrentTransferWizardLine(models.TransientModel):
    _name = 'stock.current.transfer.wizard.line'
    _description = 'Stock Current Transfer Wizard Line'
    
    # Fields
    wizard_id = fields.Many2one('stock.current.transfer.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    source_location_id = fields.Many2one('stock.location', string='Source Location', required=True)
    available_quantity = fields.Float(string='Available Quantity', readonly=True)
    quantity_to_transfer = fields.Float(string='Quantity to Transfer', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    
    # Constraints
    @api.constrains('quantity_to_transfer')
    def _check_quantity(self):
        """Validate transfer quantity against available quantity"""
        
    @api.onchange('product_id', 'source_location_id')
    def _onchange_product_location(self):
        """Update available quantity when product or location changes"""
```

## 2. View Specifications

### 2.1 Wizard Form View Structure

```xml
<record id="view_stock_current_transfer_wizard_form" model="ir.ui.view">
    <field name="name">stock.current.transfer.wizard.form</field>
    <field name="model">stock.current.transfer.wizard</field>
    <field name="arch" type="xml">
        <form string="Create Stock Transfer">
            <sheet>
                <group>
                    <group>
                        <field name="source_location_id" readonly="1"/>
                        <field name="destination_location_id" required="1"/>
                        <field name="picking_type_id" invisible="1"/>
                    </group>
                    <group>
                        <field name="immediate_transfer"/>
                        <field name="scheduled_date" attrs="{'invisible': [('immediate_transfer', '=', True)]}"/>
                    </group>
                </group>
                <notebook>
                    <page string="Products">
                        <field name="line_ids">
                            <tree editable="bottom">
                                <field name="product_id"/>
                                <field name="source_location_id"/>
                                <field name="available_quantity"/>
                                <field name="quantity_to_transfer"/>
                                <field name="uom_id"/>
                            </tree>
                        </field>
                    </page>
                    <page string="Notes">
                        <field name="notes" nolabel="1"/>
                    </page>
                </notebook>
            </sheet>
            <footer>
                <button name="action_create_transfer" type="object" string="Create Transfer" class="btn-primary"/>
                <button string="Cancel" class="btn-secondary" special="cancel"/>
            </footer>
        </form>
    </field>
</record>
```

### 2.2 Enhanced Kanban View with Selection

```xml
<!-- Add selection checkbox to kanban card -->
<div class="o_kanban_record_top">
    <div class="float-start">
        <input type="checkbox" class="product-selection-checkbox" 
               t-att-data-product-id="record.product_id.raw_value"
               t-att-data-location-id="record.location_id.raw_value"
               t-att-data-quantity="record.quantity.raw_value"
               t-att-data-uom-id="record.uom_id.raw_value"/>
    </div>
    <!-- existing kanban content -->
</div>
```

### 2.3 Enhanced List View with Selection

```xml
<!-- Add selection column to tree view -->
<tree string="Current Stock Report" edit="false" create="false" delete="false">
    <field name="product_id" widget="selection" create="false" edit="false"/>
    <!-- existing fields -->
</tree>
```

## 3. JavaScript Specifications

### 3.1 Selection Manager Component

```javascript
class ProductSelectionManager extends Component {
    setup() {
        this.selectedProducts = useState(new Map());
        this.orm = useService("orm");
        this.action = useService("action");
    }
    
    toggleProductSelection(productId, locationId, quantity, uomId) {
        const key = `${productId}_${locationId}`;
        if (this.selectedProducts.has(key)) {
            this.selectedProducts.delete(key);
        } else {
            this.selectedProducts.set(key, {
                productId,
                locationId,
                quantity,
                uomId
            });
        }
    }
    
    async openTransferWizard() {
        if (this.selectedProducts.size === 0) {
            this.notification.add("Please select at least one product", { type: "warning" });
            return;
        }
        
        const selectedData = Array.from(this.selectedProducts.values());
        return this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'stock.current.transfer.wizard',
            view_mode: 'form',
            target: 'new',
            context: {
                default_selected_products: selectedData
            }
        });
    }
}
```

### 3.2 Enhanced Kanban Controller

```javascript
export class StockKanbanWithTransferController extends KanbanController {
    setup() {
        super.setup();
        this.selectionManager = new ProductSelectionManager();
    }
}
```

## 4. Security Specifications

### 4.1 Access Rights

```xml
<!-- Access rights for transfer wizard -->
<record id="access_stock_current_transfer_wizard_user" model="ir.model.access">
    <field name="name">stock.current.transfer.wizard user</field>
    <field name="model_id" ref="model_stock_current_transfer_wizard"/>
    <field name="group_id" ref="stock.group_stock_user"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="True"/>
    <field name="perm_unlink" eval="True"/>
</record>

<record id="access_stock_current_transfer_wizard_line_user" model="ir.model.access">
    <field name="name">stock.current.transfer.wizard.line user</field>
    <field name="model_id" ref="model_stock_current_transfer_wizard_line"/>
    <field name="group_id" ref="stock.group_stock_user"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="True"/>
    <field name="perm_unlink" eval="True"/>
</record>
```

## 5. CSS Specifications

### 5.1 Selection UI Styling

```css
/* Product selection checkbox styling */
.product-selection-checkbox {
    margin-right: 8px;
    transform: scale(1.2);
}

/* Selected product highlighting */
.kanban-card-selected {
    border: 2px solid #007bff;
    background-color: #f8f9fa;
}

/* Transfer button styling */
.transfer-selected-button {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 1000;
}

/* Quantity validation styling */
.quantity-warning {
    color: #dc3545;
    font-weight: bold;
}
```

## 6. Integration Points

### 6.1 Model Integration

The transfer wizard will integrate with:
- `stock.picking` - For creating the transfer
- `stock.move` - For creating individual product moves
- `stock.quant` - For quantity validation
- `product.product` - For product information

### 6.2 View Integration

The feature will integrate with existing views:
- `view_stock_current_report_kanban` - Enhanced with selection
- `view_stock_current_report_tree` - Enhanced with selection
- New wizard views for transfer creation

### 6.3 JavaScript Integration

The JavaScript will extend existing controllers:
- `StockKanbanController` - Enhanced with selection functionality
- `StockListController` - Enhanced with selection functionality

## 7. Data Flow

### 7.1 Product Selection Flow

1. User selects products in kanban/list view
2. JavaScript tracks selected products in memory
3. User clicks "Transfer Selected" button
4. JavaScript opens wizard with selected product data
5. Wizard pre-populates with selected products

### 7.2 Transfer Creation Flow

1. User configures destination location and quantities
2. Wizard validates quantities against available stock
3. User confirms transfer creation
4. Wizard creates stock picking and moves
5. System validates transfer (if immediate)
6. User is redirected to created transfer

## 8. Error Handling

### 8.1 Validation Errors

- Insufficient quantity warnings
- Invalid destination locations
- Missing required fields
- Permission denied errors

### 8.2 System Errors

- Database transaction failures
- Concurrent modification conflicts
- Network connectivity issues
- Server-side processing errors

## 9. Performance Considerations

### 9.1 Database Optimization

- Efficient queries for available quantities
- Batch processing for multiple products
- Minimal locking during transfer creation

### 9.2 UI Optimization

- Lazy loading of product details
- Efficient selection tracking
- Minimal DOM manipulation

## 10. Testing Strategy

### 10.1 Unit Tests

- Wizard model validation
- Quantity calculation accuracy
- Transfer creation logic

### 10.2 Integration Tests

- End-to-end transfer workflow
- View interaction testing
- JavaScript functionality

### 10.3 Performance Tests

- Large dataset handling
- Concurrent user scenarios
- Memory usage optimization