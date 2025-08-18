#!/bin/bash
# Script to monitor Odoo logs for valuation debugging

echo "=== Monitoring Odoo logs for valuation debugging ==="
echo "Please create and validate a transfer in another terminal, then check the output below:"
echo ""

# Follow logs and filter for our debugging messages
sudo journalctl -u instance1 -f | grep -E "tqt|valuation|force|_should_valuate|_action_done|SVL|accounting"
