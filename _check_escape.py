# Verify the double-escaping in scratchpad.py
s = 'hello "world"'
# What the code actually does (from line 135):
# text_escaped = text.replace('"', '\\\\"')
escaped_wrong = s.replace('"', '\\\\"')
print('WRONG result repr:', repr(escaped_wrong))

# What it should be:
escaped_correct = s.replace('"', '\\"')
print('CORRECT result repr:', repr(escaped_correct))

print('Are they different?', escaped_wrong != escaped_correct)
print()

# Let's check what the actual file has:
with open(r'D:\translate-project\yak-browser-use\backend\engine\scratchpad.py', 'r') as f:
    lines = f.readlines()
    line_135 = lines[134]  # 0-indexed
    print('Line 135 raw:', repr(line_135))
