/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

// Base Chart Component
export class DashboardChart extends Component {
    static template = "buz_warranty_management.DashboardChart";
    static props = {
        ...standardFieldProps,
    };
    
    static extractProps({ attrs, field }) {
        return {
            chartId: attrs.chartId || attrs.chartid || field.name,
        };
    }
    
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.chart = null;
        this.canvasRef = useRef("canvasRef");
        this.state = useState({
            loading: true,
            error: false,
            errorMessage: ''
        });
        
        onMounted(() => {
            // Delay rendering to ensure Chart.js is loaded
            setTimeout(() => {
                this.renderChart();
            }, 100);
        });
        
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }
    
    renderChart() {
        const canvas = this.canvasRef.el;
        if (!canvas) {
            console.error("Canvas element not found");
            this.state.error = true;
            this.state.errorMessage = "Canvas not found";
            this.state.loading = false;
            return;
        }
        
        const ctx = canvas.getContext('2d');
        // Get chart data from props record
        const chartData = this.props.record.data[this.props.name];
        
        if (!chartData) {
            console.warn("No chart data provided for field:", this.props.name);
            this.state.error = true;
            this.state.errorMessage = "No data available";
            this.state.loading = false;
            return;
        }
        
        try {
            // Parse JSON if needed
            const data = typeof chartData === 'string' ? JSON.parse(chartData) : chartData;
            
            console.log("Rendering chart:", this.props.name, "Type:", data.type);
            
            // Check if Chart.js is available
            if (typeof window.Chart !== 'undefined') {
                this.renderChartWithChartJS(data);
            } else {
                console.error("Chart.js library not loaded");
                this.state.error = true;
                this.state.errorMessage = "Chart.js not loaded";
            }
            
            this.state.loading = false;
        } catch (error) {
            console.error("Error rendering chart:", error);
            this.state.error = true;
            this.state.errorMessage = error.message;
            this.state.loading = false;
        }
    }
    
    renderChartWithChartJS(data) {
        const ctx = this.canvasRef.el.getContext('2d');
        
        // Destroy existing chart
        if (this.chart) {
            this.chart.destroy();
        }
        
        try {
            // Create new chart with Chart.js
            this.chart = new window.Chart(ctx, {
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
            
            console.log("Chart created successfully:", this.props.name);
        } catch (error) {
            console.error("Error creating Chart.js instance:", error);
            this.state.error = true;
            this.state.errorMessage = "Failed to create chart: " + error.message;
            throw error;
        }
    }
    
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
            
            // Call drill-down handler
            this.props.onChartClick(clickData);
        }
    }
    
    onChartHover(event, elements) {
        if (this.canvasRef && this.canvasRef.el) {
            this.canvasRef.el.style.cursor = elements.length > 0 ? 'pointer' : 'default';
        }
    }
    
    updateChart(newData) {
        if (this.chart && newData) {
            const data = typeof newData === 'string' ? JSON.parse(newData) : newData;
            
            if (typeof Chart !== 'undefined') {
                // Update Chart.js chart
                this.chart.data = data.data;
                this.chart.options = data.options;
                this.chart.update('active');
            } else {
                // Update simple chart
                this.chart.data = data.data;
                this.chart.options = data.options;
                this.chart.render();
            }
        }
    }
    
    exportChart(format = 'png') {
        if (!this.chart) {
            this.notification.add(
                "Chart not available for export",
                { type: "warning" }
            );
            return;
        }
        
        try {
            if (format === 'png') {
                if (typeof Chart !== 'undefined') {
                    const url = this.chart.toBase64Image();
                    const link = document.createElement('a');
                    link.download = `${this.props.chartId}_${new Date().toISOString().split('T')[0]}.png`;
                    link.href = url;
                    link.click();
                } else {
                    // Simple chart fallback
                    this.notification.add(
                        "PNG export not available with simple charts",
                        { type: "info" }
                    );
                }
            } else if (format === 'jpg') {
                if (typeof Chart !== 'undefined') {
                    const url = this.chart.toBase64Image('image/jpeg', 0.9);
                    const link = document.createElement('a');
                    link.download = `${this.props.chartId}_${new Date().toISOString().split('T')[0]}.jpg`;
                    link.href = url;
                    link.click();
                } else {
                    // Simple chart fallback
                    this.notification.add(
                        "JPG export not available with simple charts",
                        { type: "info" }
                    );
                }
            }
            
            this.notification.add(
                `Chart exported as ${format.toUpperCase()}`,
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                "Failed to export chart: " + error.message,
                { type: "danger" }
            );
        }
    }
}

// Pie Chart Component
export class PieChart extends DashboardChart {
    static template = "buz_warranty_management.PieChart";
    
    static extractProps({ attrs, field }) {
        return {
            ...super.extractProps({ attrs, field }),
            chartId: attrs.chartId || attrs.chartid || field.name,
        };
    }
    
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

// Line Chart Component
export class LineChart extends DashboardChart {
    static template = "buz_warranty_management.LineChart";
    
    static extractProps({ attrs, field }) {
        return {
            ...super.extractProps({ attrs, field }),
            chartId: attrs.chartId || attrs.chartid || field.name,
        };
    }
    
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

// Bar Chart Component
export class BarChart extends DashboardChart {
    static template = "buz_warranty_management.BarChart";
    
    static extractProps({ attrs, field }) {
        return {
            ...super.extractProps({ attrs, field }),
            chartId: attrs.chartId || attrs.chartid || field.name,
        };
    }
    
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


// Register specialized components as field widgets
registry.category("fields").add("dashboard_chart", {
    component: DashboardChart,
    extractProps: DashboardChart.extractProps,
});

registry.category("fields").add("pie_chart", {
    component: PieChart,
    extractProps: PieChart.extractProps,
});

registry.category("fields").add("line_chart", {
    component: LineChart,
    extractProps: LineChart.extractProps,
});

registry.category("fields").add("bar_chart", {
    component: BarChart,
    extractProps: BarChart.extractProps,
});