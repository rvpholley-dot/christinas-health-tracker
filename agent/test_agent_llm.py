"""Tests for agent_llm pure helpers. Run:
C:\\Python313\\python.exe agent\\test_agent_llm.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_llm

fails = 0


def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails += 1


IMG_BLOCKS = [{"type": "image", "source": {"type": "base64",
              "media_type": "image/png", "data": "AAAA"}},
              {"type": "text", "text": "(photo saved) look!"}]

# consecutive user turns where the second is block content must NOT be
# string-concatenated (that raises TypeError without the isinstance guard)
out = agent_llm._merge_alternating([
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hey"},
    {"role": "user", "content": "one"},
    {"role": "user", "content": IMG_BLOCKS},
])
check("block turn survives merge", out[-1]["content"] == IMG_BLOCKS)
check("string turns still merge", agent_llm._merge_alternating(
    [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
)[0]["content"] == "a\nb")
check("leading non-user still dropped", agent_llm._merge_alternating(
    [{"role": "assistant", "content": "x"}, {"role": "user", "content": "y"}]
)[0]["role"] == "user")

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
