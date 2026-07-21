/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ZONE_TYPES } from "@buz_smart_warehouse/js/layout_designer";

const ZONE_COLORS = Object.fromEntries(ZONE_TYPES.map((z) => [z.id, z.color]));

/**
 * Read-only SVG floor plan of the designed warehouse layout, with racks
 * colored by occupancy. Geometry mirrors the Layout Designer canvas.
 */
export class WarehouseMap2D extends Component {
    static template = "buz_smart_warehouse.Map2D";
    static props = {
        map: Object,
        highlightIds: { type: Array, optional: true },
        onLocationClick: { type: Function, optional: true },
    };

    get floor() {
        return this.props.map.floor || { w: 70, h: 45 };
    }

    get racks() {
        return (this.props.map.racks || []).filter(
            (rack) => rack.layout && rack.layout.positioned
        );
    }

    get docks() {
        return (this.props.map.docks || []).filter((dock) => dock.positioned);
    }

    elementsOf(type) {
        return (this.props.map.elements || []).filter(
            (element) => element.element_type === type
        );
    }

    zoneColor(element) {
        return ZONE_COLORS[element.zone_type] || "#94a3b8";
    }

    dockLayout(dock) {
        const layout = dock.layout || {};
        return {
            width: layout.width || 4.0,
            depth: layout.depth || 8.0,
        };
    }

    rackPct(rack) {
        const pcts = rack.locations
            .map((loc) => loc.pct)
            .filter((pct) => pct !== null && pct !== undefined);
        return pcts.length
            ? pcts.reduce((a, b) => a + b, 0) / pcts.length
            : null;
    }

    rackFill(rack) {
        const pct = this.rackPct(rack);
        if (pct === null) {
            return "#e2e8f0";
        }
        if (pct >= 85) {
            return "#f5b5b5";
        }
        if (pct >= 60) {
            return "#f7e3a1";
        }
        return "#b6e2c3";
    }

    rackStroke(rack) {
        const pct = this.rackPct(rack);
        if (pct === null) {
            return "#64748b";
        }
        if (pct >= 85) {
            return "#d64545";
        }
        if (pct >= 60) {
            return "#b7791f";
        }
        return "#2f855a";
    }

    rackPctLabel(rack) {
        const pct = this.rackPct(rack);
        return pct === null ? "" : Math.round(pct) + "%";
    }

    bayLines(rack) {
        const lines = [];
        const bays = Math.max(1, (rack.layout && rack.layout.bays) || 1);
        const cols = bays * 2;
        for (let i = 1; i < cols; i++) {
            lines.push((rack.layout.width / cols) * i);
        }
        return lines;
    }

    isHit(rack) {
        const ids = this.props.highlightIds || [];
        return (
            ids.length && rack.locations.some((loc) => ids.includes(loc.id))
        );
    }

    isDimmed(rack) {
        const ids = this.props.highlightIds || [];
        return ids.length && !rack.locations.some((loc) => ids.includes(loc.id));
    }

    onRackClick(rack) {
        if (rack.id && this.props.onLocationClick) {
            this.props.onLocationClick(rack.id, rack.name);
        }
    }
}
