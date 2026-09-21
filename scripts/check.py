#!/usr/bin/env python3
"""
CryptoTrace Sentinel (SIH26183) — Full Project Health & Test Check
Runs backend pytest, validator unittests, frontend vitest, and frontend build.
"""
import sys
import subprocess
import os

def run_step(name: str, cmd: list, cwd: str = None) -> bool:
    print(f"\n==========================================")
    print(f"[*] Running: {name}")
    print(f"[*] Command: {' '.join(cmd)}")
    print(f"==========================================")
    result = subprocess.run(cmd, cwd=cwd, shell=False)
    if result.returncode != 0:
        print(f"\n[!] FAILED: {name} (exit code {result.returncode})")
        return False
    print(f"[+] PASSED: {name}")
    return True

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    frontend_dir = os.path.join(root_dir, "frontend")

    # Determine npm executable name (npm.cmd on Windows)
    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"

    steps = [
        ("Backend Pytest Test Suite", [sys.executable, "-m", "pytest", "backend/tests"], root_dir),
        ("Address Validator Unit Tests", [sys.executable, "test_validator.py"], root_dir),
        ("Frontend Vitest Unit Tests", [npm_cmd, "run", "test"], frontend_dir),
        ("Frontend Production Typecheck & Build", [npm_cmd, "run", "build"], frontend_dir),
    ]

    for name, cmd, cwd in steps:
        success = run_step(name, cmd, cwd)
        if not success:
            print("\n[!] Check pipeline aborted due to failure.")
            sys.exit(1)

    print("\n==========================================")
    print("[+] ALL CHECKS PASSED SUCCESSFULLY!")
    print("==========================================\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
