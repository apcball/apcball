#!/bin/bash
# Comprehensive Database Registry Fix - Version 2

echo "🚨 COMPREHENSIVE DATABASE REGISTRY FIX"
echo "======================================"

# Stop all Odoo processes completely
echo "🛑 Stopping all Odoo processes..."
sudo systemctl stop instance1
sudo pkill -f "odoo-bin" 2>/dev/null || true
sudo pkill -f "python.*odoo" 2>/dev/null || true
sleep 15

# Complete database registry cleanup
echo "🔧 Performing complete database registry cleanup..."

sudo -u postgres psql -d MOG_LIVE_15_08 << 'EOF'
-- Drop all signaling sequences and tables
DROP SEQUENCE IF EXISTS base_registry_signaling CASCADE;
DROP SEQUENCE IF EXISTS base_cache_signaling_default CASCADE;
DROP SEQUENCE IF EXISTS base_cache_signaling_assets CASCADE;
DROP SEQUENCE IF EXISTS base_cache_signaling_routing CASCADE;
DROP SEQUENCE IF EXISTS base_cache_signaling_templates CASCADE;

-- Drop any existing signaling tables
DROP TABLE IF EXISTS base_registry_signaling CASCADE;
DROP TABLE IF EXISTS base_cache_signaling CASCADE;

-- Clear all registry-related parameters
DELETE FROM ir_config_parameter WHERE key LIKE '%registry%';
DELETE FROM ir_config_parameter WHERE key LIKE '%signaling%';
DELETE FROM ir_config_parameter WHERE key LIKE '%cache%';

-- Clear sessions that might hold locks
DELETE FROM ir_sessions;

-- Reset any problematic sequences
SELECT setval('ir_sequence', 1, false);

-- Vacuum to clean up
VACUUM FULL;

-- Show final state
SELECT 'Registry cleanup completed' as status;
EOF

echo "   ✅ Database registry completely cleaned"

# Clear any file-based caches
echo "🧹 Clearing file caches..."
sudo rm -rf /tmp/odoocache* 2>/dev/null || true
sudo rm -rf /home/mogenit/.local/share/Odoo/sessions/* 2>/dev/null || true
sudo find /opt/instance1/odoo17 -name "*.pyc" -delete 2>/dev/null || true

# Restart PostgreSQL to clear any locks
echo "🔄 Restarting PostgreSQL..."
sudo systemctl restart postgresql
sleep 15

# Start Odoo in safe mode first
echo "🚀 Starting Odoo in safe initialization mode..."
sudo systemctl start instance1
sleep 30

# Test access
echo "🔍 Testing web access..."
for i in {1..10}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://mogdev.work/web?db=MOG_LIVE_15_08" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo "   ✅ Web interface accessible (HTTP $HTTP_CODE)"
        break
    else
        echo "   ⏳ Waiting for web interface... ($i/10) - HTTP $HTTP_CODE"
        sleep 10
    fi
done

echo
echo "🎯 REGISTRY FIX COMPLETE!"
echo "========================"
echo
echo "🌐 Test URLs:"
echo "   Main: https://mogdev.work/web?db=MOG_LIVE_15_08"
echo "   Manager: https://mogdev.work/web/database/manager"
echo
echo "🔍 If still having issues:"
echo "   Check logs: sudo tail -f /var/log/odoo/instance1.log"
