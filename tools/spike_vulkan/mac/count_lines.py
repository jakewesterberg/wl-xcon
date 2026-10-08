"""Spike S: non-blank, non-comment lines (a line whose first non-space characters are
`//` is a comment, including `//!` and `///`; trailing comments count as code; neither
file has block comments). usage: count_lines.py <file>..."""
import sys

for path in sys.argv[1:]:
    lines = open(path, encoding="utf-8").read().splitlines()
    assert not any("/*" in l for l in lines), f"{path} has a block comment"
    code = [l for l in lines if l.strip() and not l.strip().startswith("//")]
    print(f"{path}: {len(lines)} lines, {len(code)} code (non-blank, non-comment)")
