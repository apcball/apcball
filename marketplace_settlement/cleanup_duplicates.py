"""
Script to clean up duplicate settlement entries
Run this in Odoo shell to remove duplicate account move lines
"""

# Find duplicate settlement moves with same reference
duplicate_moves = env['account.move'].search([('ref', 'like', 'SETTLE-%')])
grouped_moves = {}

for move in duplicate_moves:
    ref = move.ref
    if ref not in grouped_moves:
        grouped_moves[ref] = []
    grouped_moves[ref].append(move)

# Find actual duplicates (more than one move with same reference)
actual_duplicates = {ref: moves for ref, moves in grouped_moves.items() if len(moves) > 1}

print(f"Found {len(actual_duplicates)} settlement references with duplicates:")
for ref, moves in actual_duplicates.items():
    print(f"  {ref}: {len(moves)} moves")
    for move in moves:
        print(f"    - Move ID: {move.id}, State: {move.state}, Date: {move.date}")

# To clean up (uncomment and run carefully):
# for ref, moves in actual_duplicates.items():
#     # Keep the first move, cancel/delete the others
#     moves_to_keep = moves[0]
#     moves_to_remove = moves[1:]
#     
#     for move in moves_to_remove:
#         if move.state == 'posted':
#             move.button_cancel()
#         move.unlink()
#     print(f"Cleaned up {len(moves_to_remove)} duplicate moves for {ref}")

print("\nTo clean up duplicates, uncomment the cleanup section and run again.")
print("Always backup your database before running cleanup operations!")
