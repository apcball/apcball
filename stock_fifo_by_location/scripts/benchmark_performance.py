#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Benchmark Script for stock_fifo_by_location v17.0.1.1.8

This script benchmarks FIFO operations before and after optimization.

Usage:
    python3 benchmark_performance.py --database=your_db --product=123 --warehouse=1
"""

import argparse
import time
from contextlib import contextmanager

try:
    import odoo
    from odoo import api, SUPERUSER_ID
except ImportError:
    print("Error: Odoo not found. Run this script from Odoo environment.")
    exit(1)


@contextmanager
def timer(name):
    """Simple timer context manager."""
    start = time.time()
    yield
    end = time.time()
    print(f"  {name}: {(end - start) * 1000:.2f} ms")


def benchmark_fifo_queue(env, product_id, warehouse_id, iterations=100):
    """Benchmark FIFO queue retrieval."""
    print("\n1. FIFO Queue Retrieval")
    print("-" * 50)
    
    product = env['product.product'].browse(product_id)
    warehouse = env['stock.warehouse'].browse(warehouse_id)
    svl_model = env['stock.valuation.layer']
    
    # Warm-up
    svl_model._get_fifo_queue(product, warehouse)
    
    # Benchmark
    with timer(f"  Get FIFO queue ({iterations} iterations)"):
        for _ in range(iterations):
            layers = svl_model._get_fifo_queue(product, warehouse)
    
    print(f"  Found {len(layers)} layers in queue")


def benchmark_fifo_cost_calculation(env, product_id, warehouse_id, quantity=100, iterations=50):
    """Benchmark FIFO cost calculation."""
    print("\n2. FIFO Cost Calculation")
    print("-" * 50)
    
    product = env['product.product'].browse(product_id)
    warehouse = env['stock.warehouse'].browse(warehouse_id)
    fifo_service = env['fifo.service']
    
    # Warm-up
    fifo_service.calculate_fifo_cost(product, warehouse, quantity)
    
    # Benchmark
    with timer(f"  Calculate FIFO cost ({iterations} iterations)"):
        for _ in range(iterations):
            result = fifo_service.calculate_fifo_cost(product, warehouse, quantity)
    
    print(f"  Result: qty={result['qty']}, cost={result['cost']:.2f}, unit_cost={result['unit_cost']:.4f}")


def benchmark_fifo_cost_with_landed_cost(env, product_id, warehouse_id, quantity=100, iterations=50):
    """Benchmark FIFO cost with landed cost calculation."""
    print("\n3. FIFO Cost with Landed Cost")
    print("-" * 50)
    
    product = env['product.product'].browse(product_id)
    warehouse = env['stock.warehouse'].browse(warehouse_id)
    fifo_service = env['fifo.service']
    
    # Warm-up
    fifo_service.calculate_fifo_cost_with_landed_cost(product, warehouse, quantity)
    
    # Benchmark
    with timer(f"  Calculate with landed cost ({iterations} iterations)"):
        for _ in range(iterations):
            result = fifo_service.calculate_fifo_cost_with_landed_cost(product, warehouse, quantity)
    
    print(f"  Result: cost={result['cost']:.2f}, landed_cost={result['landed_cost']:.2f}")


def benchmark_batch_calculation(env, products_warehouses, iterations=20):
    """Benchmark batch FIFO calculation."""
    print("\n4. Batch FIFO Calculation")
    print("-" * 50)
    
    fifo_service = env['fifo.service']
    batch_input = [(p, wh, 100) for p, wh in products_warehouses]
    
    print(f"  Batch size: {len(batch_input)} items")
    
    # Warm-up
    fifo_service.calculate_fifo_cost_batch(batch_input)
    
    # Benchmark batch
    with timer(f"  Batch calculation ({iterations} iterations)"):
        for _ in range(iterations):
            results = fifo_service.calculate_fifo_cost_batch(batch_input)
    
    # Benchmark individual (for comparison)
    with timer(f"  Individual calculation ({iterations} iterations)"):
        for _ in range(iterations):
            for product_id, warehouse_id, qty in batch_input:
                product = env['product.product'].browse(product_id)
                warehouse = env['stock.warehouse'].browse(warehouse_id)
                fifo_service.calculate_fifo_cost(product, warehouse, qty)
    
    print(f"  Results: {len(results)} items calculated")


def benchmark_landed_cost_lookup(env, product_id, warehouse_id, iterations=100):
    """Benchmark landed cost lookup."""
    print("\n5. Landed Cost Lookup")
    print("-" * 50)
    
    product = env['product.product'].browse(product_id)
    warehouse = env['stock.warehouse'].browse(warehouse_id)
    svl_model = env['stock.valuation.layer']
    
    # Warm-up
    svl_model.get_landed_cost_at_warehouse(product, warehouse)
    
    # Benchmark
    with timer(f"  Get landed cost ({iterations} iterations)"):
        for _ in range(iterations):
            total_lc = svl_model.get_landed_cost_at_warehouse(product, warehouse)
    
    print(f"  Total landed cost: {total_lc:.2f}")


def check_indexes(env):
    """Check if performance indexes exist."""
    print("\n6. Index Status Check")
    print("-" * 50)
    
    indexes = [
        'stock_valuation_layer_fifo_queue_idx',
        'stock_valuation_layer_warehouse_balance_idx',
        'stock_valuation_layer_product_wh_idx',
        'svl_landed_cost_layer_wh_idx',
        'svl_landed_cost_product_wh_idx',
    ]
    
    env.cr.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE indexname = ANY(%s)
    """, (indexes,))
    
    found_indexes = [row[0] for row in env.cr.fetchall()]
    
    for idx in indexes:
        status = "✅" if idx in found_indexes else "❌"
        print(f"  {status} {idx}")
    
    if len(found_indexes) < len(indexes):
        print("\n  ⚠️  Missing indexes! Run module upgrade to create them.")
        print("  Command: odoo-bin -d your_db -u stock_fifo_by_location --stop-after-init")


def get_statistics(env, product_id, warehouse_id):
    """Get database statistics."""
    print("\n7. Database Statistics")
    print("-" * 50)
    
    # Count layers
    env.cr.execute("""
        SELECT 
            COUNT(*) as total_layers,
            COUNT(*) FILTER (WHERE remaining_qty > 0) as active_layers,
            COUNT(*) FILTER (WHERE warehouse_id = %s) as warehouse_layers
        FROM stock_valuation_layer
        WHERE product_id = %s
    """, (warehouse_id, product_id))
    
    stats = env.cr.fetchone()
    print(f"  Total layers: {stats[0]}")
    print(f"  Active layers (remaining_qty > 0): {stats[1]}")
    print(f"  Layers at warehouse: {stats[2]}")
    
    # Count landed costs
    env.cr.execute("""
        SELECT COUNT(*)
        FROM stock_valuation_layer_landed_cost
        WHERE warehouse_id = %s
    """, (warehouse_id,))
    
    lc_count = env.cr.fetchone()[0]
    print(f"  Landed cost records: {lc_count}")


def main():
    """Run all benchmarks."""
    parser = argparse.ArgumentParser(description='Benchmark stock_fifo_by_location performance')
    parser.add_argument('--database', required=True, help='Database name')
    parser.add_argument('--product', type=int, required=True, help='Product ID to test')
    parser.add_argument('--warehouse', type=int, required=True, help='Warehouse ID to test')
    parser.add_argument('--products', type=int, nargs='+', help='Additional product IDs for batch test')
    parser.add_argument('--iterations', type=int, default=50, help='Number of iterations per test')
    
    args = parser.parse_args()
    
    # Initialize Odoo
    odoo.tools.config.parse_config(['--database', args.database])
    
    print("=" * 70)
    print("Performance Benchmark - stock_fifo_by_location v17.0.1.1.8")
    print("=" * 70)
    print(f"Database: {args.database}")
    print(f"Product ID: {args.product}")
    print(f"Warehouse ID: {args.warehouse}")
    print("=" * 70)
    
    with api.Environment.manage():
        registry = odoo.registry(args.database)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            # Check indexes first
            check_indexes(env)
            
            # Get statistics
            get_statistics(env, args.product, args.warehouse)
            
            # Run benchmarks
            benchmark_fifo_queue(env, args.product, args.warehouse, args.iterations)
            benchmark_fifo_cost_calculation(env, args.product, args.warehouse, 100, args.iterations)
            benchmark_fifo_cost_with_landed_cost(env, args.product, args.warehouse, 100, args.iterations)
            benchmark_landed_cost_lookup(env, args.product, args.warehouse, args.iterations)
            
            # Batch test if multiple products provided
            if args.products:
                products_warehouses = [(p, args.warehouse) for p in [args.product] + args.products]
                benchmark_batch_calculation(env, products_warehouses, args.iterations // 2)
            
            print("\n" + "=" * 70)
            print("Benchmark completed!")
            print("=" * 70)


if __name__ == '__main__':
    main()
