# JavaScript Chart Components Implementation

## 1. Chart.js Integration

### 1.1 Update __manifest__.py

Add Chart.js library to the assets:

```xml
'assets': {
    'web.assets_backend': [
        'buz_warranty_management/static/src/scss/warranty_styles.scss',
        'buz_warranty_management/static/src/scss/dashboard_indicators.scss',
        'buz_warranty_management/static/src/js/dashboard_auto_refresh.js',
        'buz_warranty_management/static/src/lib/chart.js',  # Chart.js library
        'buz_warranty_management/static/src/js/dashboard_charts.js',  # Our chart components
        'buz_warranty_management/static/src/scss/dashboard_charts.scss',  # Chart styles
    ],
},
```

### 1.2 Download Chart.js

Download Chart.js v3.9.1 and place in:
`buz_warranty_management/static/src/lib/chart.js`

## 2. Chart Component Architecture

### 2.1 Base Chart Component

Create `buz_warranty_management/static/src/js/dashboard_charts.js`:

```javascript
/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Base Chart Component
export class DashboardChart extends Component {
    static template = "buz_warranty_management.DashboardChart";
    
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.chart = null;
        this.canvasRef = null;
    }
    
    onMounted() {
        this.renderChart();
    }
    
    onWillUnmount() {
        if (this.chart) {
            this.chart.destroy();
        }
    }
    
    renderChart() {
        const canvas = this.canvasRef;
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const chartData = this.props.chartData;
        
        if (!chartData) {
            console.warn("No chart data provided");
            return;
        }
        
        // Parse JSON if needed
        const data = typeof chartData === 'string' ? JSON.parse(chartData) : chartData;
        
        // Destroy existing chart
        if (this.chart) {
            this.chart.destroy();
        }
        
        // Create new chart
        this.chart = new Chart(ctx, {
            type: data.type,
            data: data.data,
            options: {
                ...data.options,
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    ...data.options?.plugins,
                    legend: {
                        display: true,
                        position: 'top',
                        ...data.options?.plugins?.legend
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        ...data.options?.plugins?.tooltip
                    }
                },
                onClick: this.onChartClick.bind(this),
                onHover: this.onChartHover.bind(this)
            }
        });
    }
    
    onChartClick(event, elements) {
        if (elements.length > 0 && this.props.onChartClick) {
            const element = elements[0];
            const datasetIndex = element.datasetIndex;
            const index = element.index;
            const label = this.chart.data.labels[index];
            const value = this.chart.data.datasets[datasetIndex].data[index];
            
            this.props.onChartClick({
                label,
                value,
                datasetIndex,
                index,
                dataset: this.chart.data.datasets[datasetIndex]
            });
        }
    }
    
    onChartHover(event, elements) {
        this.canvasRef.style.cursor = elements.length > 0 ? 'pointer' : 'default';
    }
    
    updateChart(newData) {
        if (this.chart && newData) {
            const data = typeof newData === 'string' ? JSON.parse(newData) : newData;
            this.chart.data = data.data;
            this.chart.options = data.options;
            this.chart.update('active');
        }
    }
}

// Register the component
registry.category("fields").add("dashboard_chart", DashboardChart);
```

### 2.2 Specialized Chart Components

#### Pie Chart Component
```javascript
export class PieChart extends DashboardChart {
    static template = "buz_warranty_management.PieChart";
    
    setup() {
        super.setup();
        this.defaultOptions = {
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        };
    }
}
```

#### Line Chart Component
```javascript
export class LineChart extends DashboardChart {
    static template = "buz_warranty_management.LineChart";
    
    setup() {
        super.setup();
        this.defaultOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        drawBorder: false,
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'top'
                }
            }
        };
    }
}
```

#### Bar Chart Component
```javascript
export class BarChart extends DashboardChart {
    static template = "buz_warranty_management.BarChart";
    
    setup() {
        super.setup();
        this.defaultOptions = {
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        drawBorder: false,
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                }
            }
        };
    }
}
```

## 3. Enhanced Dashboard Controller

Update `buz_warranty_management/static/src/js/dashboard_auto_refresh.js`:

```javascript
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

const { onMounted, onWillUnmount, useState } = owl;

export class WarrantyDashboardController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        
        this.refreshInterval = null;
        this.countdownInterval = null;
        this.refreshIntervalTime = 5 * 60 * 1000;
        this.checkIntervalTime = 30 * 1000;
        
        // Chart state
        this.charts = useState({
            status: null,
            trend: null,
            comparison: null,
            products: null,
            customers: null,
            types: null,
            expiry: null
        });
        
        onMounted(() => {
            this.startAutoRefresh();
            this.initializeCharts();
        });
        
        onWillUnmount(() => {
            this.stopAutoRefresh();
            this.destroyCharts();
        });
    }
    
    initializeCharts() {
        // Initialize chart containers
        this.setupChartContainers();
        
        // Load initial chart data
        this.loadAllChartData();
    }
    
    setupChartContainers() {
        // Setup chart containers with proper dimensions
        const chartContainers = document.querySelectorAll('.chart-container');
        chartContainers.forEach(container => {
            container.style.position = 'relative';
            container.style.height = '300px';
        });
    }
    
    async loadAllChartData() {
        try {
            const record = this.model.root.data;
            
            // Load chart data from cache
            this.charts.status = record.warranty_status_chart;
            this.charts.trend = record.claims_trend_chart;
            this.charts.comparison = record.monthly_comparison_chart;
            this.charts.products = record.top_products_chart;
            this.charts.customers = record.top_customers_chart;
            this.charts.types = record.claim_types_chart;
            this.charts.expiry = record.warranty_expiry_chart;
            
            // Render charts
            this.renderAllCharts();
            
        } catch (error) {
            console.error("Error loading chart data:", error);
            this.notification.add(
                "Failed to load chart data",
                { type: "danger" }
            );
        }
    }
    
    renderAllCharts() {
        // This will be handled by the OWL components
        // The components will automatically re-render when state changes
    }
    
    destroyCharts() {
        // Clean up chart instances
        Object.values(this.charts).forEach(chart => {
            if (chart && chart.destroy) {
                chart.destroy();
            }
        });
    }
    
    // Chart interaction handlers
    onChartClick(chartType, data) {
        console.log(`Chart clicked: ${chartType}`, data);
        
        // Implement drill-down functionality
        switch (chartType) {
            case 'status':
                this.drillDownWarrantyStatus(data);
                break;
            case 'products':
                this.drillDownProducts(data);
                break;
            case 'customers':
                this.drillDownCustomers(data);
                break;
            case 'trend':
                this.drillDownClaimsTrend(data);
                break;
            default:
                console.log('No drill-down defined for', chartType);
        }
    }
    
    drillDownWarrantyStatus(data) {
        const statusMap = {
            'Active': 'active',
            'Expired': 'expired',
            'Draft': 'draft',
            'Cancelled': 'cancelled'
        };
        
        const status = statusMap[data.label];
        if (status) {
            this.actionService.doAction({
                type: 'ir.actions.act_window',
                res_model: 'warranty.card',
                view_mode: 'tree,form',
                domain: [['state', '=', status]],
                name: `${data.label} Warranties`
            });
        }
    }
    
    drillDownProducts(data) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['product_id.product_tmpl_id.name', '=', data.label]],
            name: `Warranties for ${data.label}`
        });
    }
    
    drillDownCustomers(data) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'warranty.card',
            view_mode: 'tree,form',
            domain: [['partner_id.name', '=', data.label]],
            name: `Warranties for ${data.label}`
        });
    }
    
    drillDownClaimsTrend(data) {
        // Extract month from label and filter claims
        const monthYear = data.label;
        // This would need more sophisticated date parsing
        console.log('Drill down to claims for:', monthYear);
    }
    
    // Enhanced auto-refresh with chart updates
    async autoRefresh() {
        try {
            await this.model.root.load();
            this.model.notify();
            
            // Reload chart data
            await this.loadAllChartData();
            
            this.startCountdown();
            
            this.notification.add(
                "Dashboard and charts refreshed",
                { type: "success" }
            );
        } catch (error) {
            console.error("Error auto-refreshing dashboard:", error);
            this.notification.add(
                "Failed to refresh dashboard: " + error.message,
                { type: "danger" }
            );
        }
    }
    
    // Export chart functionality
    exportChart(chartId, format = 'png') {
        const chart = this.getChartById(chartId);
        if (!chart) {
            this.notification.add(
                "Chart not found",
                { type: "warning" }
            );
            return;
        }
        
        if (format === 'png') {
            const url = chart.toBase64Image();
            const link = document.createElement('a');
            link.download = `${chartId}_chart.png`;
            link.href = url;
            link.click();
        } else if (format === 'pdf') {
            // This would require additional PDF library integration
            this.notification.add(
                "PDF export not yet implemented",
                { type: "info" }
            );
        }
    }
    
    getChartById(chartId) {
        // Find chart instance by ID
        const canvas = document.querySelector(`#${chartId}`);
        return canvas ? Chart.getChart(canvas) : null;
    }
}

export const warrantyDashboardView = {
    ...formView,
    Controller: WarrantyDashboardController,
};

registry.category("views").add("warranty_dashboard_form", warrantyDashboardView);
```

## 4. XML Templates

Create `buz_warranty_management/static/src/xml/dashboard_charts.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<templates id="template" xml:space="preserve">
    
    <!-- Base Chart Template -->
    <t t-name="buz_warranty_management.DashboardChart" owl="1">
        <div class="chart-container" t-att-class="props.containerClass or ''">
            <div class="chart-header" t-if="props.title">
                <h5 class="chart-title"><t t-esc="props.title"/></h5>
                <div class="chart-actions" t-if="props.showActions">
                    <button class="btn btn-sm btn-outline-secondary" 
                            t-on-click="() => this.exportChart(props.chartId, 'png')">
                        <i class="fa fa-download"/> PNG
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" 
                            t-on-click="() => this.exportChart(props.chartId, 'pdf')">
                        <i class="fa fa-file-pdf-o"/> PDF
                    </button>
                </div>
            </div>
            <canvas t-ref="canvasRef" 
                    t-att-id="props.chartId"
                    t-att-height="props.height or 300"/>
            <div class="chart-loading" t-if="!props.chartData">
                <i class="fa fa-spinner fa-spin"/> Loading chart...
            </div>
        </div>
    </t>
    
    <!-- Pie Chart Template -->
    <t t-name="buz_warranty_management.PieChart" owl="1">
        <div class="chart-container pie-chart">
            <div class="chart-header">
                <h5 class="chart-title"><t t-esc="props.title"/></h5>
            </div>
            <canvas t-ref="canvasRef" 
                    t-att-id="props.chartId"
                    height="300"/>
        </div>
    </t>
    
    <!-- Line Chart Template -->
    <t t-name="buz_warranty_management.LineChart" owl="1">
        <div class="chart-container line-chart">
            <div class="chart-header">
                <h5 class="chart-title"><t t-esc="props.title"/></h5>
            </div>
            <canvas t-ref="canvasRef" 
                    t-att-id="props.chartId"
                    height="300"/>
        </div>
    </t>
    
    <!-- Bar Chart Template -->
    <t t-name="buz_warranty_management.BarChart" owl="1">
        <div class="chart-container bar-chart">
            <div class="chart-header">
                <h5 class="chart-title"><t t-esc="props.title"/></h5>
            </div>
            <canvas t-ref="canvasRef" 
                    t-att-id="props.chartId"
                    height="300"/>
        </div>
    </t>
    
</templates>
```

## 5. Chart Styles

Create `buz_warranty_management/static/src/scss/dashboard_charts.scss`:

```scss
// Chart container styles
.chart-container {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    padding: 20px;
    margin-bottom: 20px;
    position: relative;
    
    .chart-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        
        .chart-title {
            margin: 0;
            font-size: 1.1rem;
            font-weight: 600;
            color: #495057;
        }
        
        .chart-actions {
            .btn {
                margin-left: 5px;
                font-size: 0.8rem;
                padding: 0.25rem 0.5rem;
            }
        }
    }
    
    .chart-loading {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: #6c757d;
        font-size: 0.9rem;
    }
}

// Specific chart type styles
.pie-chart {
    canvas {
        max-height: 300px;
    }
}

.line-chart, .bar-chart {
    canvas {
        max-height: 400px;
    }
}

// Responsive design
@media (max-width: 768px) {
    .chart-container {
        padding: 15px;
        
        .chart-header {
            flex-direction: column;
            align-items: flex-start;
            
            .chart-actions {
                margin-top: 10px;
            }
        }
    }
}

// Chart animation styles
.chart-container {
    canvas {
        transition: opacity 0.3s ease;
        
        &:hover {
            opacity: 0.9;
        }
    }
}

// Chart legend customization
.chart-container {
    .chart-legend {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        margin-top: 10px;
        
        .legend-item {
            display: flex;
            align-items: center;
            margin: 0 10px 5px 0;
            font-size: 0.85rem;
            
            .legend-color {
                width: 12px;
                height: 12px;
                border-radius: 2px;
                margin-right: 5px;
            }
        }
    }
}

// Chart tooltip customization
.chart-tooltip {
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 0.85rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
```

## 6. Integration with Dashboard View

Update the dashboard view XML to include chart components:

```xml
<!-- Charts Section -->
<div class="row mb-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">Warranty Status Distribution</h5>
            </div>
            <div class="card-body">
                <widget name="dashboard_chart" 
                        chart_id="warranty_status_chart"
                        chart_data="warranty_status_chart"
                        title="Warranty Status"
                        chart_type="pie"
                        show_actions="true"/>
            </div>
        </div>
    </div>
    
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">Claims Trend</h5>
            </div>
            <div class="card-body">
                <widget name="dashboard_chart" 
                        chart_id="claims_trend_chart"
                        chart_data="claims_trend_chart"
                        title="Monthly Claims Trend"
                        chart_type="line"
                        show_actions="true"/>
            </div>
        </div>
    </div>
</div>
```

This implementation provides a comprehensive JavaScript foundation for interactive dashboard charts with Chart.js, including:
- Reusable chart components
- Interactive features (click, hover, drill-down)
- Export functionality
- Responsive design
- Smooth animations
- Integration with existing dashboard auto-refresh