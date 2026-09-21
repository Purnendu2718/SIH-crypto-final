"""
Paste-and-send runner for PROJECT.md (same file format as your original script).

Improvements over the original:
  * reads a per-phase wait from a line like  <!-- wait: 900 -->  (falls back to --default-wait)
  * --start / --end to resume after a crash or run a subset (e.g. --start 6)
  * --dry-run prints the plan without touching keyboard or clipboard
  * checks the clipboard really holds the phase before pasting
  * mouse into any screen corner aborts (pyautogui failsafe)
  * appends a timestamped log to run_phases.log

Usage:
  python run_phases.py                 # all phases
  python run_phases.py --start 6       # resume from Phase 6
  python run_phases.py --dry-run
"""

import argparse
import re
import sys
import time
from datetime import datetime, timedelta

SPLIT = "### Phase"  # identical to the original script, so PROJECT.md stays compatible


def load_phases(path):
    text = open(path, "r", encoding="utf-8").read()
    phases = []
    for chunk in (p for p in text.split(SPLIT) if p.strip()):
        full = SPLIT + chunk
        m = re.match(r"### Phase\s+(\d+)", full)
        num = int(m.group(1)) if m else len(phases)
        w = re.search(r"<!--\s*wait:\s*(\d+)\s*-->", full)
        phases.append({"num": num, "text": full, "wait": int(w.group(1)) if w else None})
    return phases


def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line)
    with open("run_phases.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="PROJECT.md")
    ap.add_argument("--start", type=int, default=0, help="first phase number to send")
    ap.add_argument("--end", type=int, default=10**6, help="last phase number to send")
    ap.add_argument("--default-wait", type=int, default=600)
    ap.add_argument("--countdown", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    todo = [p for p in load_phases(a.file) if a.start <= p["num"] <= a.end]
    if not todo:
        sys.exit("No phases selected.")
    waits = [p["wait"] or a.default_wait for p in todo]
    total = sum(waits)
    print(f"{len(todo)} phases, about {timedelta(seconds=total)} of waiting in total.")
    for p, w in zip(todo, waits):
        print(f"  Phase {p['num']:>2}: {len(p['text']):>6} chars, wait {w}s")
    if a.dry_run:
        return

    import pyautogui
    import pyperclip

    pyautogui.FAILSAFE = True
    mod = "command" if sys.platform == "darwin" else "ctrl"

    print(f"\nSwitch to the Antigravity window and click the chat box. Starting in {a.countdown}s "
          f"(move the mouse into a screen corner to abort)...")
    time.sleep(a.countdown)

    for p, w in zip(todo, waits):
        pyperclip.copy(p["text"])
        time.sleep(0.3)
        if pyperclip.paste() != p["text"]:
            sys.exit(f"Clipboard mismatch on Phase {p['num']}; stopping. Resume with --start {p['num']}")
        pyautogui.hotkey(mod, "v")
        time.sleep(1.0)  # let a long paste finish rendering
        pyautogui.press("enter")
        log(f"Sent Phase {p['num']} ({len(p['text'])} chars). Waiting {w}s "
            f"(resume point if you stop: --start {p['num'] + 1})")
        time.sleep(w)

    log("All selected phases sent.")


if __name__ == "__main__":
    main()
