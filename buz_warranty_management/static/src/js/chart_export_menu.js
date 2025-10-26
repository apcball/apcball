/** @odoo-module **/

import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Chart Export Menu Field Widget Component
export class ChartExportMenu extends Component {
    static template = "buz_warranty_management.ChartExportMenu";
    static props = {
        ...standardFieldProps,
        chart_id: { type: String, optional: true },
    };
    
    setup() {
        this.notification = useService("notification");
    }
    
    exportChart(format) {
        // Get chart_id from props or record value
        const chartId = this.props.chart_id || this.props.record.data[this.props.name];
        
        if (!chartId) {
            this.notification.add(
                "No chart ID provided",
                { type: "warning" }
            );
            return;
        }
        
        // Find the chart component in the DOM
        const chartElement = document.querySelector(`canvas[id="${chartId}"]`);
        
        if (!chartElement) {
            this.notification.add(
                "Chart not found",
                { type: "warning" }
            );
            return;
        }
        
        // Try to find parent component with export capability
        let currentElement = chartElement.parentElement;
        let chartComponent = null;
        
        while (currentElement && !chartComponent) {
            if (currentElement.__owl__ && currentElement.__owl__.component) {
                const comp = currentElement.__owl__.component;
                if (comp.exportChart && typeof comp.exportChart === 'function') {
                    chartComponent = comp;
                    break;
                }
            }
            currentElement = currentElement.parentElement;
        }
        
        if (chartComponent && chartComponent.exportChart) {
            chartComponent.exportChart(format);
        } else {
            this.notification.add(
                "Chart export not available",
                { type: "warning" }
            );
        }
    }
    
    exportAsPNG(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.exportChart('png');
    }
    
    exportAsJPG(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.exportChart('jpg');
    }
    
    exportAsPDF(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.exportChart('pdf');
    }
    
    exportDataAsCSV(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.exportChart('csv');
    }
}

// Register as a field widget
registry.category("fields").add("chart_export_menu", {
    component: ChartExportMenu,
});