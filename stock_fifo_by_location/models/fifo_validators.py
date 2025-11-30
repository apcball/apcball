# -*- coding: utf-8 -*-
"""
FIFO Validators

Common validation logic to reduce duplication.
"""

from odoo import _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class FifoValidator:
    """
    Centralized validation logic for FIFO operations.
    """
    
    @staticmethod
    def validate_product(product, require_fifo=True):
        """
        Validate product for FIFO operations.
        
        Args:
            product: product.product record
            require_fifo: If True, product must use FIFO costing
            
        Raises:
            UserError if validation fails
        """
        if not product:
            raise UserError(_('Product is required.'))
        
        if product.type != 'product':
            raise UserError(_(
                'Product %s is not a storable product. '
                'FIFO tracking only applies to storable products.'
            ) % product.display_name)
        
        if require_fifo and product.categ_id.property_cost_method != 'fifo':
            raise UserError(_(
                'Product %s does not use FIFO costing method. '
                'Current method: %s'
            ) % (product.display_name, product.categ_id.property_cost_method))
    
    @staticmethod
    def validate_warehouse(warehouse):
        """
        Validate warehouse.
        
        Args:
            warehouse: stock.warehouse record
            
        Raises:
            UserError if validation fails
        """
        if not warehouse:
            raise UserError(_('Warehouse is required.'))
        
        if not warehouse.lot_stock_id:
            raise UserError(_(
                'Warehouse %s does not have a stock location configured.'
            ) % warehouse.display_name)
    
    @staticmethod
    def validate_quantity(quantity, precision_digits=2, allow_zero=False, allow_negative=False):
        """
        Validate quantity value.
        
        Args:
            quantity: Quantity to validate
            precision_digits: Decimal precision
            allow_zero: Allow zero quantity
            allow_negative: Allow negative quantity
            
        Raises:
            UserError if validation fails
            
        Returns:
            float: Validated quantity
        """
        if not allow_negative and float_compare(quantity, 0, precision_digits=precision_digits) < 0:
            raise UserError(_('Quantity cannot be negative: %s') % quantity)
        
        if not allow_zero and float_compare(quantity, 0, precision_digits=precision_digits) == 0:
            raise UserError(_('Quantity cannot be zero.'))
        
        return quantity
    
    @staticmethod
    def validate_cost(cost, allow_zero=False, allow_negative=False):
        """
        Validate cost value.
        
        Args:
            cost: Cost to validate
            allow_zero: Allow zero cost
            allow_negative: Allow negative cost
            
        Raises:
            UserError if validation fails
            
        Returns:
            float: Validated cost
        """
        if not allow_negative and cost < 0:
            raise UserError(_('Cost cannot be negative: %s') % cost)
        
        if not allow_zero and cost == 0:
            raise UserError(_('Cost cannot be zero.'))
        
        return cost
    
    @staticmethod
    def validate_fifo_availability(product, warehouse, quantity, env, raise_error=True):
        """
        Validate FIFO availability at warehouse.
        
        Args:
            product: product.product record
            warehouse: stock.warehouse record
            quantity: Quantity needed
            env: Odoo environment
            raise_error: Raise error if insufficient (or return result dict)
            
        Returns:
            dict: Availability information
            
        Raises:
            UserError if raise_error=True and insufficient
        """
        fifo_service = env['fifo.service']
        
        result = fifo_service.validate_warehouse_availability(
            product, warehouse, quantity,
            allow_fallback=not raise_error,
            company_id=env.company.id
        )
        
        return result
    
    @staticmethod
    def validate_warehouse_consistency(layer):
        """
        Validate warehouse consistency for valuation layer.
        
        Args:
            layer: stock.valuation.layer record
            
        Raises:
            ValidationError if inconsistent
        """
        if not layer.warehouse_id and layer.quantity != 0:
            raise ValidationError(_(
                'Valuation layer %s has quantity but no warehouse assigned. '
                'All layers with non-zero quantity must have a warehouse.'
            ) % layer.id)
        
        # Validate move and warehouse match
        if layer.stock_move_id and layer.warehouse_id:
            move = layer.stock_move_id
            expected_wh = None
            
            if layer.quantity > 0 and move.location_dest_id:
                expected_wh = move.location_dest_id.warehouse_id
            elif layer.quantity < 0 and move.location_id:
                expected_wh = move.location_id.warehouse_id
            
            if expected_wh and expected_wh.id != layer.warehouse_id.id:
                # This is a warning, not an error (can happen in some edge cases)
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(
                    'Warehouse mismatch: Layer %s has warehouse %s but expected %s',
                    layer.id, layer.warehouse_id.name, expected_wh.name
                )
    
    @staticmethod
    def validate_inter_warehouse_transfer(source_wh, dest_wh, product, quantity):
        """
        Validate inter-warehouse transfer.
        
        Args:
            source_wh: Source warehouse
            dest_wh: Destination warehouse
            product: Product
            quantity: Quantity
            
        Raises:
            UserError if validation fails
        """
        FifoValidator.validate_warehouse(source_wh)
        FifoValidator.validate_warehouse(dest_wh)
        FifoValidator.validate_product(product)
        FifoValidator.validate_quantity(quantity)
        
        if source_wh.id == dest_wh.id:
            raise UserError(_(
                'Cannot transfer to the same warehouse. '
                'Source and destination must be different.'
            ))
    
    @staticmethod
    def validate_return_move(move, original_move):
        """
        Validate return move against original.
        
        Args:
            move: Return move
            original_move: Original move being returned
            
        Raises:
            UserError if validation fails
        """
        if not original_move:
            raise UserError(_('Original move not found for return.'))
        
        if move.product_id.id != original_move.product_id.id:
            raise UserError(_(
                'Return move product (%s) does not match original move product (%s).'
            ) % (move.product_id.display_name, original_move.product_id.display_name))
        
        # Allow return quantity greater than original (but warn)
        if move.product_qty > original_move.product_qty:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                'Return quantity (%.2f) exceeds original move quantity (%.2f) for move %s',
                move.product_qty, original_move.product_qty, move.name
            )


class FifoErrorMessages:
    """
    Centralized error message templates.
    """
    
    @staticmethod
    def shortage_error(product, warehouse, needed, available, fallback_warehouses=None):
        """
        Generate shortage error message.
        
        Args:
            product: Product
            warehouse: Warehouse
            needed: Quantity needed
            available: Quantity available
            fallback_warehouses: List of alternative warehouses
            
        Returns:
            str: Formatted error message
        """
        shortage = needed - available
        uom = product.uom_id.name if product.uom_id else 'Unit'
        
        msg = (
            f"❌ สินค้าไม่เพียงพอในคลัง!\n\n"
            f"สินค้า: {product.display_name}\n"
            f"คลัง: {warehouse.name}\n"
            f"มีอยู่: {available:.2f} {uom}\n"
            f"ต้องการ: {needed:.2f} {uom}\n"
            f"ขาด: {shortage:.2f} {uom}\n\n"
        )
        
        if fallback_warehouses:
            msg += "💡 คลังอื่นที่มีสินค้า:\n"
            for fb in fallback_warehouses[:5]:
                msg += f"   • {fb['warehouse_name']}: {fb['available_qty']:.2f} {uom}\n"
            msg += "\n🔧 แนะนำ: สร้าง Internal Transfer เพื่อโอนสินค้ามายังคลังนี้\n"
        else:
            msg += (
                "⚠️ ไม่พบสินค้าในคลังอื่น\n\n"
                "🔧 แนะนำ:\n"
                "   1. สั่งซื้อสินค้าจาก Supplier\n"
                "   2. ตรวจสอบ Receipt ที่ยังไม่ได้ Validate\n"
                "   3. ตรวจสอบ Inventory Adjustment\n"
            )
        
        return msg
    
    @staticmethod
    def negative_balance_error(product, warehouse, current_qty, consuming_qty, fallback_warehouses=None):
        """
        Generate negative balance error message.
        
        Args:
            product: Product
            warehouse: Warehouse
            current_qty: Current quantity
            consuming_qty: Quantity being consumed
            fallback_warehouses: Alternative warehouses
            
        Returns:
            str: Formatted error message
        """
        qty_after = current_qty + consuming_qty  # consuming_qty is negative
        uom = product.uom_id.name if product.uom_id else 'Unit'
        
        msg = (
            f"❌ คลัง {warehouse.name} จะติดลบ!\n\n"
            f"สินค้า: {product.display_name}\n"
            f"จำนวนคงเหลือปัจจุบัน: {current_qty:.2f} {uom}\n"
            f"พยายามตัดออก: {abs(consuming_qty):.2f} {uom}\n"
            f"จะเหลือ: {qty_after:.2f} {uom} (ติดลบ!)\n\n"
        )
        
        if fallback_warehouses:
            msg += "🏭 คลังอื่นที่มีสินค้า:\n"
            for fb in fallback_warehouses[:3]:
                msg += f"   • {fb['warehouse_name']}: {fb['available_qty']:.2f} {uom}\n"
            msg += "\n➡️ แนะนำ: โอนสินค้าจากคลังอื่นมายังคลังนี้ก่อน\n\n"
        
        msg += (
            "🔧 วิธีแก้ไข:\n"
            "   1. ถ้าเป็นการ Return: ตรวจสอบว่า Return ไปคลังที่ถูกต้อง\n"
            "   2. ถ้าเป็นการขาย: โอนสินค้าจากคลังอื่นมาก่อน\n"
            "   3. ตรวจสอบว่ามีการรับสินค้าเข้าถูกต้อง\n"
            "   4. ตรวจสอบ Inventory Adjustment ที่อาจทำให้ Stock ลดลง\n"
        )
        
        return msg
