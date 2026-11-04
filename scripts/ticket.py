"""Tiny helper for the local-markdown wayfinder tracker: resolve a ticket.

usage: python scripts/ticket.py resolve NN "answer text"
       python scripts/ticket.py claim NN
"""
import re, sys
from pathlib import Path

ISSUES = Path(__file__).resolve().parents[1] / ".scratch/ii2202-quant/issues"

def find(nn):
    (f,) = ISSUES.glob(f"{int(nn):02d}-*.md")
    return f

def set_status(text, status):
    return re.sub(r"^Status: .*$", f"Status: {status}", text, count=1, flags=re.M)

cmd, nn = sys.argv[1], sys.argv[2]
f = find(nn)
t = f.read_text()
if cmd == "claim":
    t = set_status(t, "claimed")
elif cmd == "resolve":
    t = set_status(t, "resolved")
    t = t.replace("## Answer\n\n", f"## Answer\n\n{sys.argv[3].strip()}\n\n", 1)
f.write_text(t)
print(f.name, "->", cmd)
