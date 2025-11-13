#!/bin/bash
# Script สำหรับติดตั้ง direct_print_odoo ใน Odoo 17

echo "=========================================="
echo "ติดตั้ง direct_print_odoo Module"
echo "=========================================="
echo ""

# หยุด Odoo service
echo "1. หยุด Odoo service..."
sudo systemctl stop instance1
sleep 3

# ติดตั้งโมดูล
echo ""
echo "2. ติดตั้งโมดูลและ dependencies..."
cd /opt/instance1/odoo17

# ใช้ virtual environment
source /opt/instance1/odoo17-venv/bin/activate

# ติดตั้งโมดูล
/opt/instance1/odoo17-venv/bin/python3 odoo-bin -c /etc/instance1.conf \
    -d MOG_LIVE_15_08 \
    -i direct_print_odoo \
    --stop-after-init \
    --log-level=info

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo "✅ ติดตั้งโมดูลสำเร็จ!"
    echo "=========================================="
else
    echo "=========================================="
    echo "❌ เกิดข้อผิดพลาดในการติดตั้ง (Exit Code: $EXIT_CODE)"
    echo "=========================================="
fi

# เริ่ม Odoo service อีกครั้ง
echo ""
echo "3. เริ่ม Odoo service..."
sudo systemctl start instance1
sleep 3

echo ""
echo "4. ตรวจสอบสถานะ Odoo..."
sudo systemctl status instance1 --no-pager | head -15