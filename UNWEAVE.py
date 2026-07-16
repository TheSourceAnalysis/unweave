#!/usr/bin/env python3

import re
import os
import sys


NOISE_RE = re.compile(r"%[^%]*%")
SET_RE = re.compile(r"^\s*set\s+([A-Za-z0-9_]+)\s*=(.*)$", re.IGNORECASE)
SUBST_RE = re.compile(r"%([A-Za-z0-9_]+)%")


def parse_vars(lines):
    vars_ = {}
    for raw in lines:
        line = raw.strip()
        if line.upper().startswith("REM"):
            continue
        cleaned = NOISE_RE.sub("", line)
        m = SET_RE.match(cleaned)
        if m:
            name = m.group(1)
            val = m.group(2)
            val = re.split(r"&?\s*REM", val, flags=re.IGNORECASE)[0].strip()
            if name not in vars_:
                vars_[name] = val
    return vars_


def expand(line, vars_, max_passes=200):
    out = line
    for _ in range(max_passes):
        prev = out
        out = SUBST_RE.sub(lambda m: vars_.get(m.group(1), m.group(0)), out)
        if out == prev:
            break
    return out


def tidy(expanded):
    s = expanded
    s = re.sub(r"\bsetlocalenabledelayedexpansion\b",
               "setlocal enabledelayedexpansion", s, flags=re.IGNORECASE)
    s = re.sub(r"\bechooff\b", "echo off", s, flags=re.IGNORECASE)
    s = re.sub(r"\bexit/b\b", "exit /b", s, flags=re.IGNORECASE)
    s = re.sub(r"headlesspowershell", "headless powershell", s, flags=re.IGNORECASE)
    s = re.sub(r"powershell\.exe-", "powershell.exe -", s, flags=re.IGNORECASE)
    s = re.sub(r"(-epbypass|-w\s*h)(-c)", r"\1 -c", s)
    return s


def is_plain_text(s):
    if SUBST_RE.search(s):
        return False
    printable = sum(1 for c in s if 32 <= ord(c) < 127 or c in "\r\n\t")
    return len(s) == 0 or printable / len(s) > 0.85


def ask(prompt, options):
    while True:
        print(prompt)
        for key, label in options:
            print(f"  [{key}] {label}")
        ans = input("> ").strip().lower()
        for key, label in options:
            if ans == key.lower():
                return key
        print("[!] Invalid choice, try again.")


def main():
    print("=" * 60)
    print("  UNWEAVE  -  NOISEWEAVE batch deobfuscator")
    print("=" * 60)

    while True:
        path = input("\nPath to the obfuscated .bat file: ").strip().strip('"')
        if os.path.isfile(path):
            break
        print("[!] File not found. Try again.")

    out_dir = os.path.dirname(os.path.abspath(path))
    base = os.path.splitext(os.path.basename(path))[0]

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    print(f"[*] Read {len(lines)} lines from {path}")

    vars_ = parse_vars(lines)
    print(f"[*] Parsed {len(vars_)} variables")

    clean_lines = []
    ps_payloads = []

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.upper().startswith("REM"):
            continue
        if not SUBST_RE.search(line):
            continue
        expanded = expand(line, vars_)
        expanded = tidy(expanded)
        if is_plain_text(expanded) and len(expanded.strip()) > 3:
            clean_lines.append(f"REM [line {idx}] resolved")
            clean_lines.append(expanded.strip())
            clean_lines.append("")
            low = expanded.lower()
            if "powershell" in low or "iex" in low or "invoke-expression" in low:
                ps_payloads.append((idx, expanded.strip()))

    if not clean_lines:
        print("[!] No NOISEWEAVE builder lines detected. File may not use this pattern.")
        sys.exit(0)

    choice = ask("\nWhat do you want to generate?",
                 [("1", ".bat"),
                  ("2", ".ps1"),
                  ("3", "both")])

    if choice in ("1", "3"):
        out_bat = os.path.join(out_dir, f"{base}_clean.bat")
        with open(out_bat, "w", encoding="utf-8") as f:
            f.write("@echo off\n")
            f.write("REM Deobfuscated by UNWEAVE\n")
            f.write("\n".join(clean_lines))
        print(f"[+] Wrote clean bat : {out_bat}")

    if choice in ("2", "3"):
        if not ps_payloads:
            ps_payloads = [(0, "\n".join(clean_lines))]
        out_ps = os.path.join(out_dir, f"{base}_clean.ps1")
        with open(out_ps, "w", encoding="utf-8") as f:
            for idx, payload in ps_payloads:
                m = re.search(r"-c\s+\"?([\s\S]*?)\"?\s*$", payload)
                body = m.group(1) if m else payload
                body = body.replace(";;", "; ")
                hdr = f"# ===== PowerShell payload from bat line {idx} =====\n" if idx else ""
                f.write(hdr + body + "\n\n")
        print(f"[+] Wrote decoded ps1: {out_ps}")

    print("[*] Done. Output is in the SAME directory as the input.")
    print("[*] Review the files - do NOT run them blindly.")


if __name__ == "__main__":
    main()
