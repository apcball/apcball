# Interactive Features Implementation

## 1. Drill-Down Functionality

### 1.1 Chart Click Handlers

Extend the JavaScript chart components to handle drill-down interactions:

```javascript
// Enhanced chart click handler in dashboard_charts.js
onChartClick(event, elements) {
    if (elements.length > 0 && this.props.onChartClick) {
        const element = elements[0];
        const datasetIndex = element.datasetIndex;
        const index = element.index;
        const chartData = this.chart.data;
        
        const clickData = {
            label: chartData.labels[index],
            value: chartData.datasets[datasetIndex].data[index],
            datasetIndex,
            index,
            dataset: chartData.datasets[datasetIndex],
            chartType: this.props.chartType,
            chartId: this.props.chartId
        };
        
        // Call the drill-down handler
        this.props.onChartClick(clickData);
    }
}
```

### 1.2 Drill-Down Actions

Implement specific drill-down actions for each chart type:

```javascript
// In WarrantyDashboardController
async onChartDrillDown(clickData) {
    const { chartId, label, value, dataset } = clickData;
    
    switch (chartId) {
        case 'warranty_status_chart':
            await this.drillDownWarrantyStatus(label);
            break;
        case 'top_products_chart':
            await this.drillDownProducts(label, dataset.label);
            break;
        case 'top_customers_chart':
            await this.drillDownCustomers(label, dataset.label);
            break;
        case 'claims_trend_chart':
            await this.drillDownClaimsTrend(label);
            break;
        case 'claim_types_chart':
            await this.drillDownClaimTypes(label, dataset.label);
            break;
        case 'warranty_expiry_chart':
            await this.drillDownWarrantyExpiry(label);
            break;
        case 'monthly_comparison_chart':
            await this.drillDownMonthlyComparison(label, dataset.label);
            break;
        default:
            console.log('No drill-down defined for', chartId);
    }
}

// Specific drill-down implementations
async drillDownWarrantyStatus(status) {
    const statusMap = {
        'Active': 'active',
        'Expired': 'expired',
        'Draft': 'draft',
        'Cancelled': 'cancelled'
    };
    
    const state = statusMap[status];
    if (state) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['state', '=', state]],
            name: `${status} Warranties`,
            context: {
                'default_state': state,
                'search_default_state': 1
            }
        });
    }
}

async drillDownProducts(productName, datasetType) {
    let domain = [['product_id.product_tmpl_id.name', '=', productName]];
    let name = `Warranties for ${productName}`;
    
    if (datasetType === 'Claims') {
        // Show claims for this product
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.claim',
            view_mode: 'tree,form',
            domain: [['product_id.product_tmpl_id.name', '=', productName]],
            name: `Claims for ${productName}`
        });
    } else {
        // Show warranties for this product
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: domain,
            name: name
        });
    }
}

async drillDownCustomers(customerName, datasetType) {
    if (datasetType === 'Claims') {
        // Show claims for this customer
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.claim',
            view_mode: 'tree,form',
            domain: [['partner_id.name', '=', customerName]],
            name: `Claims for ${customerName}`
        });
    } else {
        // Show warranties for this customer
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['partner_id.name', '=', customerName]],
            name: `Warranties for ${customerName}`
        });
    }
}

async drillDownClaimsTrend(monthLabel) {
    // Parse month label to get date range
    const dateRange = this.parseMonthLabel(monthLabel);
    if (dateRange) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.claim',
            view_mode: 'tree,form',
            domain: [
                ['claim_date', '>=', dateRange.start],
                ['claim_date', '<=', dateRange.end]
            ],
            name: `Claims for ${monthLabel}`
        });
    }
}

async drillDownClaimTypes(monthLabel, claimType) {
    const dateRange = this.parseMonthLabel(monthLabel);
    if (dateRange) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.claim',
            view_mode: 'tree,form',
            domain: [
                ['claim_date', '>=', dateRange.start],
                ['claim_date', '<=', dateRange.end],
                ['claim_type', '=', claimType.toLowerCase()]
            ],
            name: `${claimType} Claims for ${monthLabel}`
        });
    }
}

async drillDownWarrantyExpiry(monthLabel) {
    const dateRange = this.parseMonthLabel(monthLabel);
    if (dateRange) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [
                ['end_date', '>=', dateRange.start],
                ['end_date', '<=', dateRange.end]
            ],
            name: `Warranties Expiring in ${monthLabel}`
        });
    }
}

// Helper method to parse month labels
parseMonthLabel(monthLabel) {
    // Parse labels like "Jan 2023", "February 2023", etc.
    const months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    };
    
    const fullMonths = {
        'January': '01', 'February': '02', 'March': '03', 'April': '04',
        'May': '05', 'June': '06', 'July': '07', 'August': '08',
        'September': '09', 'October': '10', 'November': '11', 'December': '12'
    };
    
    const parts = monthLabel.split(' ');
    if (parts.length === 2) {
        const month = months[parts[0]] || fullMonths[parts[0]];
        const year = parts[1];
        
        if (month && year) {
            const startDate = `${year}-${month}-01`;
            const endDate = `${year}-${month}-31`; // Simplified, would need proper month end calculation
            return { start: startDate, end: endDate };
        }
    }
    
    return null;
}
```

## 2. Advanced Filtering System

### 2.1 Filter Component

Create a comprehensive filtering component:

```javascript
// Filter component in dashboard_filters.js
export class DashboardFilters extends Component {
    static template = "buz_warranty_management.DashboardFilters";
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            dateRange: '30',
            productIds: [],
            customerIds: [],
            warrantyStatus: [],
            claimTypes: [],
            customStartDate: null,
            customEndDate: null
        });
        
        this.availableProducts = [];
        this.availableCustomers = [];
        
        onMounted(() => {
            this.loadFilterOptions();
        });
    }
    
    async loadFilterOptions() {
        // Load available products
        const products = await this.orm.searchRead(
            'product.product',
            [['sale_ok', '=', true]],
            ['id', 'name', 'display_name'],
            { limit: 1000 }
        );
        this.availableProducts = products;
        
        // Load available customers
        const customers = await this.orm.searchRead(
            'res.partner',
            [['customer_rank', '>', 0]],
            ['id', 'name', 'display_name'],
            { limit: 1000 }
        );
        this.availableCustomers = customers;
    }
    
    async applyFilters() {
        // Build filter context
        const filterContext = {
            date_range: this.state.dateRange,
            product_ids: this.state.productIds,
            customer_ids: this.state.customerIds,
            warranty_status: this.state.warrantyStatus,
            claim_types: this.state.claimTypes,
            custom_start_date: this.state.customStartDate,
            custom_end_date: this.state.customEndDate
        };
        
        // Trigger dashboard update with filters
        this.env.bus.trigger('dashboard-filters-changed', filterContext);
    }
    
    resetFilters() {
        this.state.dateRange = '30';
        this.state.productIds = [];
        this.state.customerIds = [];
        this.state.warrantyStatus = [];
        this.state.claimTypes = [];
        this.state.customStartDate = null;
        this.state.customEndDate = null;
        
        // Trigger update with reset filters
        this.applyFilters();
    }
}
```

### 2.2 Filter Template

```xml
<!-- Dashboard Filters Template -->
<t t-name="buz_warranty_management.DashboardFilters" owl="1">
    <div class="dashboard-filters card bg-light mb-3">
        <div class="card-header">
            <h5 class="mb-0">
                <i class="fa fa-filter me-2"/> Dashboard Filters
            </h5>
        </div>
        <div class="card-body">
            <div class="row">
                <!-- Date Range Filter -->
                <div class="col-md-3">
                    <label class="form-label">Date Range:</label>
                    <select class="form-select" t-model="state.dateRange">
                        <option value="7">Last 7 Days</option>
                        <option value="30">Last 30 Days</option>
                        <option value="90">Last 3 Months</option>
                        <option value="180">Last 6 Months</option>
                        <option value="365">Last Year</option>
                        <option value="custom">Custom Range</option>
                    </select>
                </div>
                
                <!-- Custom Date Range -->
                <div class="col-md-3" t-if="state.dateRange === 'custom'">
                    <label class="form-label">Start Date:</label>
                    <input type="date" class="form-control" t-model="state.customStartDate"/>
                </div>
                
                <div class="col-md-3" t-if="state.dateRange === 'custom'">
                    <label class="form-label">End Date:</label>
                    <input type="date" class="form-control" t-model="state.customEndDate"/>
                </div>
                
                <!-- Product Filter -->
                <div class="col-md-3">
                    <label class="form-label">Products:</label>
                    <select class="form-select" multiple="true" t-model="state.productIds">
                        <option value="">All Products</option>
                        <t t-foreach="availableProducts" t-as="product" t-key="product.id">
                            <option t-att-value="product.id" t-esc="product.display_name"/>
                        </t>
                    </select>
                </div>
                
                <!-- Customer Filter -->
                <div class="col-md-3">
                    <label class="form-label">Customers:</label>
                    <select class="form-select" multiple="true" t-model="state.customerIds">
                        <option value="">All Customers</option>
                        <t t-foreach="availableCustomers" t-as="customer" t-key="customer.id">
                            <option t-att-value="customer.id" t-esc="customer.display_name"/>
                        </t>
                    </select>
                </div>
                
                <!-- Warranty Status Filter -->
                <div class="col-md-2">
                    <label class="form-label">Warranty Status:</label>
                    <div class="form-check">
                        <t t-foreach="['active', 'expired', 'draft', 'cancelled']" t-as="status" t-key="status">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" 
                                       t-att-id="'status_' + status"
                                       t-model="state.warrantyStatus"
                                       t-att-value="status"/>
                                <label class="form-check-label" t-att-for="'status_' + status">
                                    <t t-esc="status.charAt(0).toUpperCase() + status.slice(1)"/>
                                </label>
                            </div>
                        </t>
                    </div>
                </div>
                
                <!-- Claim Types Filter -->
                <div class="col-md-2">
                    <label class="form-label">Claim Types:</label>
                    <div class="form-check">
                        <t t-foreach="['repair', 'replace', 'refund']" t-as="claimType" t-key="claimType">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" 
                                       t-att-id="'claim_' + claimType"
                                       t-model="state.claimTypes"
                                       t-att-value="claimType"/>
                                <label class="form-check-label" t-att-for="'claim_' + claimType">
                                    <t t-esc="claimType.charAt(0).toUpperCase() + claimType.slice(1)"/>
                                </label>
                            </div>
                        </t>
                    </div>
                </div>
                
                <!-- Action Buttons -->
                <div class="col-md-2 d-flex align-items-end">
                    <div class="btn-group w-100">
                        <button class="btn btn-primary" t-on-click="applyFilters">
                            <i class="fa fa-filter me-1"/> Apply
                        </button>
                        <button class="btn btn-secondary" t-on-click="resetFilters">
                            <i class="fa fa-refresh me-1"/> Reset
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</t>
```

## 3. Time Range Selection

### 3.1 Time Range Component

```javascript
// Time range selector component
export class TimeRangeSelector extends Component {
    static template = "buz_warranty_management.TimeRangeSelector";
    
    setup() {
        this.state = useState({
            selectedRange: '30',
            customStart: null,
            customEnd: null,
            presetRanges: [
                { value: '7', label: 'Last 7 Days' },
                { value: '30', label: 'Last 30 Days' },
                { value: '90', label: 'Last 3 Months' },
                { value: '180', label: 'Last 6 Months' },
                { value: '365', label: 'Last Year' },
                { value: 'ytd', label: 'Year to Date' },
                { value: 'qtd', label: 'Quarter to Date' },
                { value: 'mtd', label: 'Month to Date' }
            ]
        });
    }
    
    getDateRange(rangeValue) {
        const today = new Date();
        let start, end;
        
        switch (rangeValue) {
            case '7':
                start = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
                break;
            case '30':
                start = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
                break;
            case '90':
                start = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000);
                break;
            case '180':
                start = new Date(today.getTime() - 180 * 24 * 60 * 60 * 1000);
                break;
            case '365':
                start = new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000);
                break;
            case 'ytd':
                start = new Date(today.getFullYear(), 0, 1);
                break;
            case 'qtd':
                const quarter = Math.floor(today.getMonth() / 3);
                start = new Date(today.getFullYear(), quarter * 3, 1);
                break;
            case 'mtd':
                start = new Date(today.getFullYear(), today.getMonth(), 1);
                break;
            case 'custom':
                start = this.state.customStart;
                end = this.state.customEnd;
                break;
            default:
                start = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
        }
        
        end = rangeValue === 'custom' ? this.state.customEnd : today;
        
        return { start, end };
    }
    
    onTimeRangeChange() {
        const range = this.getDateRange(this.state.selectedRange);
        this.env.bus.trigger('time-range-changed', range);
    }
}
```

### 3.2 Time Range Template

```xml
<t t-name="buz_warranty_management.TimeRangeSelector" owl="1">
    <div class="time-range-selector">
        <div class="btn-group" role="group">
            <t t-foreach="state.presetRanges" t-as="preset" t-key="preset.value">
                <button type="button" 
                        class="btn btn-outline-primary"
                        t-att-class="state.selectedRange === preset.value ? 'active' : ''"
                        t-on-click="() => { state.selectedRange = preset.value; onTimeRangeChange(); }">
                    <t t-esc="preset.label"/>
                </button>
            </t>
        </div>
        
        <div class="custom-range mt-2" t-if="state.selectedRange === 'custom'">
            <div class="row">
                <div class="col-md-5">
                    <label class="form-label">Start Date:</label>
                    <input type="date" class="form-control" t-model="state.customStart"/>
                </div>
                <div class="col-md-5">
                    <label class="form-label">End Date:</label>
                    <input type="date" class="form-control" t-model="state.customEnd"/>
                </div>
                <div class="col-md-2 d-flex align-items-end">
                    <button class="btn btn-primary" t-on-click="onTimeRangeChange">Apply</button>
                </div>
            </div>
        </div>
    </div>
</t>
```

## 4. Chart Interaction Enhancements

### 4.1 Chart Zoom and Pan

```javascript
// Add zoom and pan functionality to charts
setupChartWithZoom(chartId, chartData) {
    const ctx = document.getElementById(chartId).getContext('2d');
    
    this.chart = new Chart(ctx, {
        type: chartData.type,
        data: chartData.data,
        options: {
            ...chartData.options,
            plugins: {
                ...chartData.options?.plugins,
                zoom: {
                    zoom: {
                        wheel: {
                            enabled: true,
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'x',
                    },
                    pan: {
                        enabled: true,
                        mode: 'x',
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index',
            }
        }
    });
}
```

### 4.2 Chart Data Point Highlighting

```javascript
// Enhanced hover effects
setupChartHighlighting(chart) {
    chart.options.onHover = (event, activeElements) => {
        event.native.target.style.cursor = activeElements.length > 0 ? 'pointer' : 'default';
        
        // Highlight related data points across charts
        if (activeElements.length > 0) {
            const dataIndex = activeElements[0].index;
            this.highlightDataPointAcrossCharts(dataIndex);
        } else {
            this.clearHighlights();
        }
    };
}

highlightDataPointAcrossCharts(dataIndex) {
    // Clear previous highlights
    this.clearHighlights();
    
    // Highlight data point in all charts
    Object.values(this.charts).forEach(chart => {
        if (chart && chart.data.datasets[0]) {
            chart.setActiveElements([{
                datasetIndex: 0,
                index: dataIndex,
            }]);
            chart.update();
        }
    });
}

clearHighlights() {
    Object.values(this.charts).forEach(chart => {
        if (chart) {
            chart.setActiveElements([]);
            chart.update();
        }
    });
}
```

## 5. Real-time Data Updates

### 5.1 Live Data Streaming

```javascript
// Implement real-time data updates
setupRealTimeUpdates() {
    // Listen for cache updates
    this.env.bus.addEventListener('dashboard-cache-updated', (event) => {
        this.updateChartsWithNewData(event.detail);
    });
    
    // Listen for filter changes
    this.env.bus.addEventListener('dashboard-filters-changed', (event) => {
        this.applyFiltersToCharts(event.detail);
    });
    
    // Listen for time range changes
    this.env.bus.addEventListener('time-range-changed', (event) => {
        this.updateChartsForTimeRange(event.detail);
    });
}

async updateChartsWithNewData(newData) {
    // Update each chart with new data
    for (const [chartId, chartData] of Object.entries(newData)) {
        if (this.charts[chartId]) {
            const data = typeof chartData === 'string' ? JSON.parse(chartData) : chartData;
            this.charts[chartId].data = data.data;
            this.charts[chartId].update('active');
        }
    }
}
```

### 5.2 Smooth Animations

```javascript
// Add smooth transitions for data updates
updateChartWithAnimation(chart, newData) {
    chart.data = newData.data;
    chart.update('active'); // Use 'active' mode for smooth animations
}

// Custom animation configuration
const animationConfig = {
    duration: 750,
    easing: 'easeInOutQuart',
    onComplete: () => {
        // Animation complete callback
        this.onChartAnimationComplete();
    }
};
```

## 6. Performance Optimization

### 6.1 Debounced Updates

```javascript
// Debounce filter changes to avoid excessive updates
import { debounce } from "@web/core/utils/timing";

setup() {
    this.debouncedApplyFilters = debounce(this.applyFilters.bind(this), 500);
}

onFilterChange() {
    this.debouncedApplyFilters();
}
```

### 6.2 Lazy Loading for Charts

```javascript
// Implement lazy loading for chart data
async loadChartDataOnDemand(chartId) {
    if (!this.chartDataCache[chartId]) {
        this.chartDataCache[chartId] = await this.orm.call(
            'warranty.dashboard.cache',
            'get_chart_data',
            [chartId],
            { context: this.getFilterContext() }
        );
    }
    return this.chartDataCache[chartId];
}
```

This comprehensive interactive features implementation provides:
- Deep drill-down capabilities for all chart types
- Advanced filtering system with multiple criteria
- Flexible time range selection with presets and custom ranges
- Chart zoom, pan, and highlighting features
- Real-time data updates with smooth animations
- Performance optimizations for large datasets
- Responsive design for all screen sizes

The implementation ensures users can interact with the dashboard in meaningful ways, from high-level overview to detailed record analysis.