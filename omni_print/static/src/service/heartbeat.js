/** @odoo-module **/

import { registry } from "@web/core/registry";

const { EventBus } = owl;

class HeartbeatConnectionService {
    constructor(url, baseInterval = 1000, maxInterval = 1000*60*60, backoffFactor = 2) {
        this.url = url;
        this.baseInterval = baseInterval;  // Base reconnection interval
        this.maxInterval = maxInterval;    // Maximum reconnection interval
        this.backoffFactor = backoffFactor;// Backoff multiplier factor
        this.retryCount = 0;               // Reconnection attempt count
        this.connection = null;            // General connection variable
        this.connectionStatus = 'closed';  // Connection status, default 'closed'
        this.bus = new EventBus()
    }

    setupConnection() {
        if (this.connection) return

        console.log("Initializing connection with heartbeat check...");
        this.connectionStatus = 'connecting'; // Update status to 'connecting'
        this.connection = new WebSocket(this.url);

        this.connection.onopen = () => {
            console.log("Connection established.");
            this.retryCount = 0;
            this.connectionStatus = 'open'; // Update status to 'open'
            this.bus.trigger("onopen")
            // this.sendHeartbeat();
        };

        this.connection.onmessage = (event) => {
            console.log("Heartbeat received: ", event.data);
            this.bus.trigger("onmessage", event)
        };

        this.connection.onerror = (event) => {
            console.log("Error observed in connection:", event);
            this.connectionStatus = 'error'; // Update status to 'error'
            this.closeConnection()
            this.bus.trigger("onerror", event)
        };

        this.connection.onclose = (event) => {
            console.log("Connection closed.");
            this.connectionStatus = 'closed'; // Update status to 'closed'
            this.closeConnection()
            this.bus.trigger("onclose", event)
            this.reconnect();
        };
    }

    reconnect() {
        const delay = Math.min(this.baseInterval * Math.pow(this.backoffFactor, this.retryCount), this.maxInterval);
        console.log(`Scheduling reconnect in ${delay} ms`);
        setTimeout(() => {
            this.setupConnection();
        }, delay);
        this.retryCount++;
    }

    closeConnection() {
        if (this.connection) {
            this.connection.close();
            this.connection = null;
            this.connectionStatus = 'closed'; // Ensure status is 'closed'
        }
    }

    isAlive() {
        return this.connectionStatus === 'open'; // Returns whether the connection is active
    }
}

const heartbeatConnectionService = {
    start() {
        const heartbeatConnectionService = new HeartbeatConnectionService('ws://127.0.0.1:32276/ping')
        heartbeatConnectionService.setupConnection()
        return heartbeatConnectionService;
    },
};

registry.category("services").add("print_heartbeat_service", heartbeatConnectionService);
