"""Move /buy, /grant, /revoke handlers before the generic handle_message."""
with open('bot/handlers/common.py', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line numbers for key markers
gen_handler_start = None  # @router.message() - the generic one
buy_start = None  # @router.message(Command("buy"))
revoke_end = None  # end of handle_revoke
send_result_start = None  # async def _send_result

for i, line in enumerate(lines):
    stripped = line.rstrip()
    if stripped == '@router.message()' and gen_handler_start is None:
        # Check that the NEXT line is handle_message (not buy)
        if i + 1 < len(lines) and 'async def handle_message' in lines[i + 1]:
            gen_handler_start = i
    if stripped == '@router.message(Command("buy"))':
        buy_start = i
    if stripped.startswith('async def _send_result'):
        send_result_start = i
    if stripped == '@router.message(Command("revoke"))':
        pass  # just track end below

# Find end of handle_revoke (blank line after it, or send_result_start)
if send_result_start is not None and buy_start is not None:
    revoke_end = send_result_start - 1
    # Trim trailing blank lines from the block
    while revoke_end > buy_start and lines[revoke_end].strip() == '':
        revoke_end -= 1
    revoke_end += 1  # keep one trailing newline

if buy_start is None or gen_handler_start is None or send_result_start is None:
    print(f"Markers: gen_handler={gen_handler_start}, buy={buy_start}, send_result={send_result_start}")
    print("FAILED: Could not find all markers")
    exit(1)

# Extract the block to move
block_to_move = lines[buy_start:revoke_end]

# Remove the block from its current position
new_lines = lines[:buy_start] + lines[revoke_end:]

# Insert the block before the generic handler (adjusting for removal offset)
# After removal, gen_handler_start might shift if buy_start < gen_handler_start
# But buy_start > gen_handler_start, so no shift needed
insert_pos = gen_handler_start
for i, line in enumerate(new_lines):
    stripped = line.rstrip()
    if stripped == '@router.message()':
        if i + 1 < len(new_lines) and 'async def handle_message' in new_lines[i + 1]:
            insert_pos = i
            break

result = new_lines[:insert_pos] + ['\n'] + block_to_move + ['\n'] + new_lines[insert_pos:]

with open('bot/handlers/common.py', 'w', encoding='utf-8', newline='') as f:
    f.writelines(result)

print(f"Moved {revoke_end - buy_start} lines from line {buy_start + 1} to before line {gen_handler_start + 1}")
print(f"File now has {len(result)} lines")
