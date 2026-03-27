/** @odoo-module */
import { Component, useEffect, useRef } from "@odoo/owl";

export class WaterfallChart extends Component {
    static template = "biz_monthly_analytic_budget.WaterfallChart";
    static props = {
        data: { type: Array, optional: true }
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chartInstance = null;
        
        useEffect(() => {
            this.renderChart();
        }, () => [this.props.data]);
    }

    renderChart() {
        if (!this.props.data || !this.canvasRef.el) return;
        
        if (this.chartInstance) {
            this.chartInstance.destroy();
        }
        
        const labels = this.props.data.map(d => d.label);
        const values = this.props.data.map(d => d.value);
        
        const colors = {
            'Total Budget': '#3B82F6',
            'Fixed Cost': '#8B5CF6',
            'Reserved': '#F59E0B',
            'Used': '#EF4444',
            'Remaining': '#10B981',
        };

        this.chartInstance = new window.Chart(this.canvasRef.el, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Budget Flow',
                    data: values,
                    backgroundColor: labels.map(l => colors[l] || '#6c757d'),
                    maxBarThickness: 50,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        padding: 12,
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        grid: { display: false }
                    },
                    y: {
                        grid: {
                            color: '#f1f5f9',
                            drawBorder: false
                        }
                    }
                }
            }
        });
    }
}
