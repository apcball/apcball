/** @odoo-module **/

import { Component, useState, useRef, useExternalListener } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { useService, useBus } from "@web/core/utils/hooks";

import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

const CONNECTION_UNKNOW = "unknown"
const CONNECTION_ONLINE = "online"
const CONNECTION_OFFLINE = "offline"

class PrintTrayMenu extends Component {
    setup() {
        this.state = useState({
            connection: CONNECTION_UNKNOW,
        })

        this.heartbeatService = useService('print_heartbeat_service')
        this.registerHeatbeatHooks(this.heartbeatService)
    }

    registerHeatbeatHooks(heartbeatService) {
        useBus(heartbeatService.bus, "onopen", () => {
            this.state.connection = CONNECTION_ONLINE
        })
        useBus(heartbeatService.bus, "onmessage", (event) => {
            this.state.connection = CONNECTION_ONLINE
        })
        useBus(heartbeatService.bus, "onerror", (event) => {
            this.state.connection = CONNECTION_UNKNOW
        })
        useBus(heartbeatService.bus, "onclose", (event) => {
            this.state.connection = CONNECTION_OFFLINE
        })

        if (heartbeatService.isAlive()) {
            this.state.connection = CONNECTION_ONLINE
        }
    }

    reconnect() {
        if (this.state.connection != "online") {
            this.heartbeatService.setupConnection()
        }
    }
}
PrintTrayMenu.template = "omni_print.PrintTrayMenu"
PrintTrayMenu.components = { Dropdown, DropdownItem }
PrintTrayMenu.props = {}
PrintTrayMenu.defaultProps = {}

registry.category("systray").add("printer_systray", { Component: PrintTrayMenu, }, { sequence: 200, },)
