"""Tests for the inbox save helper. Run:
C:\\Python313\\python.exe agent\\test_telegram_media.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram_loop

fails = 0


def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails += 1


tmp = tempfile.mkdtemp()
config = {"inbox_dir": tmp}

p1 = telegram_loop.save_inbox_file(config, b"12345", ".jpg", "photo")
check("file written", open(p1, "rb").read() == b"12345")
check("dated subfolder + kind in name",
      os.sep.join(p1.split(os.sep)[-2:]).count("-") >= 3
      and "photo" in os.path.basename(p1) and p1.endswith(".jpg"))
p2 = telegram_loop.save_inbox_file(config, b"67890", ".jpg", "photo")
check("same-second collision gets a distinct name", p1 != p2)
check("collision file also written", open(p2, "rb").read() == b"67890")
p3 = telegram_loop.save_inbox_file(config, b"x", "", "document")
check("missing extension falls back to .bin", p3.endswith(".bin"))

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
