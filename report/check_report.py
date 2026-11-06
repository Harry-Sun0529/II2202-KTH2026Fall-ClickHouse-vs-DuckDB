"""Gate 4: checks on the compiled report.

1. LaTeX log: no errors, no undefined references or citations, no overfull box
   wider than 10 pt; no "??" in the PDF text.
2. The Discussion section has at least 100 words.
3. Numbers:
   a. every entry of numbers_manifest.csv still equals the current CSV value
      (so numbers.tex and the tables are not stale), and its text is in the
      generated .tex files;
   b. independently, every number token in the expanded report body is either a
      design constant listed below (with its reason) or matches a value in
      results/stats/*.csv after one of a few unit conversions and the same
      rounding. Unmatched tokens fail the gate.
Writes report/number_check.csv and prints a summary; exits non-zero on failure.
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

import pandas as pd
import pymupdf

REP = Path(__file__).resolve().parent
ROOT = REP.parent
ST = ROOT / "results" / "stats"
GIB = 1024 ** 3

# Design constants that may appear in the text without coming from a CSV.
WHITELIST = {
    "0": "ClickHouse fills unmatched rows with 0 (explanation of the Q13 edit); 0 in join_use_nulls context",
    "1": "SF1; slope 1; join_use_nulls = 1; 'n > 0' style bounds",
    "2": "sampling interval 2 ms (config.yaml memory_sampler.interval_ms); 'two' style counts",
    "3": "3 loads per engine and SF (config.yaml repetitions.load); n = 3; 3 GiB spill threshold",
    "4": "4 CPUs / 4 threads (config.yaml container_limits.cpus)",
    "5": "5 % target half-width (plan 5.3 item 5); n = 5; 5 loads recommended (research plan)",
    "6": "n = 6, smallest n with an exact 95 % CI (order_stat_k(6) = 1, tested)",
    "7": "7 GiB engine memory limit (config.yaml)",
    "8": "8 GiB container limit; 8 queries; 8 cold runs in the research plan",
    "10": "SF10; 10 % CV threshold (plan 5.1); n = 10",
    "12": "12 loads = 2 engines x 2 SF x 3 (config.yaml)",
    "15": "n = 15 (plan 5.3 item 5)",
    "20": "20 warm runs (config.yaml repetitions.warm); n = 20; research plan H2: within 20 %",
    "21": "21 runs per block = 1 cold + 20 warm",
    "75": "theoretical coverage 1 - 2 (1/2)^3 = 75 % of the bootstrap CI at n = 3 (tested in test_stats.py)",
    "95": "95 % confidence level",
    "40": "proposed cap of 40 warm runs per combination (Table 5, a plan for the full study)",
    "10000": "10,000 bootstrap resamples (analysis/stats.py B_DEFAULT)",
    "0.001": "display bound '< 0.001' for p-values in Table 3",
    "3.12": "python:3.12-slim base image (docker/duckdb/Dockerfile)",
}
CONVERSIONS = {
    "identity": lambda v: v, "percent": lambda v: v * 100, "GiB": lambda v: v / GIB,
    "GB": lambda v: v / 1e9, "MB": lambda v: v / 1e6, "ms->s": lambda v: v / 1000,
}


# --------------------------------------------------------------------------- 1. log
def check_log() -> list[str]:
    issues = []
    log = (REP / "main.log").read_text(errors="replace")
    if re.search(r"^! ", log, re.M) or re.search(r"^\S+\.tex:\d+: ", log, re.M):
        issues.append("LaTeX errors in main.log")
    for m in re.finditer(r"(Reference|Citation) `([^']+)' on page \d+ undefined", log):
        issues.append(f"undefined {m.group(1).lower()} {m.group(2)}")
    if "There were undefined references" in log:
        issues.append("undefined references remain")
    for m in re.finditer(r"Overfull \\hbox \(([\d.]+)pt too wide\)", log):
        if float(m.group(1)) > 10:
            issues.append(f"overfull hbox {m.group(1)} pt")
    text = "".join(p.get_text() for p in pymupdf.open(REP / "main.pdf"))
    if "??" in text:
        issues.append("'??' in PDF text")
    return issues


# --------------------------------------------------------------------------- 2. discussion
def discussion_words() -> int:
    """Words of the Discussion section, counted on the .tex source with macros expanded
    and floats removed (the PDF text would also count figure labels and page headers)."""
    macros = dict(re.findall(r"\\csname v@(.+?)\\endcsname\{(.*)\}$", (REP / "numbers.tex").read_text(), re.M))
    tex = re.sub(r"(?m)(?<!\\)%.*$", "", (REP / "main.tex").read_text())
    sec = tex[tex.index(r"\section{Discussion (e)}") + len(r"\section{Discussion (e)}"):]
    sec = sec[:sec.index(r"\section{")]
    sec = re.sub(r"\\begin\{(figure|table)\}.*?\\end\{\1\}", " ", sec, flags=re.S)
    sec = re.sub(r"\\V\{([^}]+)\}", lambda m: macros[m.group(1)], sec)
    sec = re.sub(r"\\(ref|label|cite)\{[^}]*\}", "X", sec)
    sec = re.sub(r"\\[a-zA-Z]+\*?", " ", sec).replace("{", " ").replace("}", " ").replace("$", " ")
    return len(re.findall(r"[A-Za-z0-9][\w'’.\-%]*", sec))


# --------------------------------------------------------------------------- 3a. manifest
def check_manifest() -> list[str]:
    issues = []
    generated = (REP / "numbers.tex").read_text() + "".join(p.read_text() for p in (REP / "tables").glob("*.tex"))
    tables = {}
    for row in csv.DictReader((REP / "numbers_manifest.csv").open()):
        f = row["file"]
        tables.setdefault(f, pd.read_csv(ST / f))
        df = tables[f]
        sel = row["selector"]
        if sel.startswith("key="):
            cur = df[df.key == sel[4:]][row["column"]]
        elif sel == "row=0":
            cur = df[row["column"]].iloc[[0]]
        elif sel.startswith("sf=10,max over engines"):
            cur = pd.Series([df[df.sf == 10][row["column"]].max()])
        else:
            m = pd.Series(True, index=df.index)
            for part in sel.split(","):
                k, v = part.split("=")
                col = df[k]
                m &= (col.astype(str) == v)
            cur = df[m][row["column"]]
        if len(cur) != 1:
            issues.append(f"manifest {row['key']}: selector matches {len(cur)} rows")
            continue
        cv, rv = cur.iloc[0], row["raw"]
        try:
            same = math.isclose(float(cv), float(rv), rel_tol=1e-9, abs_tol=1e-12)
        except ValueError:
            same = str(cv) == rv
        if not same:
            issues.append(f"manifest {row['key']}: CSV now {cv}, report built with {rv} (stale)")
        if row["shown"] not in generated:
            issues.append(f"manifest {row['key']}: shown text '{row['shown']}' not in generated files")
    return issues


# --------------------------------------------------------------------------- 3b. tokens
def expanded_body() -> str:
    macros = {}
    for m in re.finditer(r"\\csname v@(.+?)\\endcsname\{(.*)\}$", (REP / "numbers.tex").read_text(), re.M):
        macros[m.group(1)] = m.group(2)
    tex = (REP / "main.tex").read_text()
    tex = re.sub(r"(?m)(?<!\\)%.*$", "", tex)
    body = tex[tex.index(r"\begin{document}"):tex.index(r"\begin{thebibliography}")]
    body = re.sub(r"\\input\{(tables/[^}]+)\}", lambda m: (REP / f"{m.group(1)}").read_text(), body)
    body = re.sub(r"\\V\{([^}]+)\}", lambda m: macros[m.group(1)], body)
    body = re.sub(r"\\(label|ref|cite|includegraphics|pageref\*?)(\[[^\]]*\])?\{[^}]*\}", " ", body)
    body = re.sub(r"\\begin\{(tabularx?|minipage|figure|table|enumerate)\}(\{[^}]*\}|\[[^\]]*\])*", " ", body)
    body = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", " ", body)
    body = re.sub(r"\[label=[^\]]*\]", " ", body)
    body = re.sub(r"\d+(\.\d+)?\\(textwidth|linewidth)", " ", body)
    body = re.sub(r"\d+(\.\d+)?(pt|em|ex|cm|mm)\b", " ", body)
    body = body.replace("--", " to ")          # ranges such as 0.93--1.02 are not negative numbers
    body = re.sub(r"(\d)\\,(\d{3})(?!\d)", r"\1\2", body)  # 10\,000 -> 10000
    body = body.replace("$-$", "-").replace("\\,", " ").replace("{,}", ",")  # 3.5\,ms -> 3.5 ms
    return body


def csv_values() -> tuple[list[tuple[float, str]], set[str]]:
    nums, strings = [], set()
    for f in sorted(ST.glob("*.csv")):
        df = pd.read_csv(f)
        for col in df.columns:
            for i, v in enumerate(df[col]):
                if isinstance(v, str):
                    strings.add(v)
                    try:
                        nums.append((float(v), f"{f.name}[{i}].{col} (text)"))
                    except ValueError:
                        pass
                    continue
                if pd.notna(v):
                    nums.append((float(v), f"{f.name}[{i}].{col}"))
    return nums, strings


def check_tokens() -> tuple[list[str], list[dict]]:
    body = expanded_body()
    nums, strings = csv_values()
    rows, issues = [], []
    # Version-like tokens (a.b.c[.d]) must equal a string in the CSVs.
    for v in re.findall(r"(?<![\w.])\d+\.\d+\.\d+(?:\.\d+)?(?:-\w+)?", body):
        ok = v in strings
        rows.append(dict(token=v, status="ok" if ok else "UNMATCHED", source="setup.csv (string)" if ok else ""))
        if not ok:
            issues.append(f"version token {v} not in CSVs")
    body = re.sub(r"(?<![\w.])\d+\.\d+\.\d+(?:\.\d+)?(?:-\w+)?", " ", body)
    for tok in re.findall(r"(?<![\w.\\])-?\d[\d,]*(?:\.\d+)?(?![\w])", body):
        t = tok.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", tok) else tok.rstrip(",")
        if t in WHITELIST or t.lstrip("-") in WHITELIST:
            rows.append(dict(token=tok, status="constant", source=WHITELIST.get(t, WHITELIST.get(t.lstrip("-")))))
            continue
        x = float(t)
        dec = len(t.split(".")[1]) if "." in t else 0
        hit = None
        for name, conv in CONVERSIONS.items():   # prefer the plain value, then unit conversions
            for v, src in nums:
                c = conv(v)
                if math.isfinite(c) and round(c, dec) == round(x, dec) and (dec > 0 or abs(c - x) < 0.5):
                    hit = f"{src} ({name})"
                    break
            if hit:
                break
        rows.append(dict(token=tok, status="ok" if hit else "UNMATCHED", source=hit or ""))
        if not hit:
            issues.append(f"number {tok} not found in results/stats/*.csv")
    return issues, rows


def main() -> int:
    issues = check_log()
    words = discussion_words()
    if words < 100:
        issues.append(f"Discussion has {words} words (< 100)")
    issues += check_manifest()
    tok_issues, rows = check_tokens()
    issues += tok_issues
    with (REP / "number_check.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["token", "status", "source"])
        w.writeheader()
        w.writerows(rows)
    n_ok = sum(r["status"] == "ok" for r in rows)
    n_const = sum(r["status"] == "constant" for r in rows)
    pages = len(pymupdf.open(REP / "main.pdf"))
    print(f"pages={pages} discussion_words={words} tokens={len(rows)} matched_csv={n_ok} constants={n_const} "
          f"manifest_entries={sum(1 for _ in open(REP / 'numbers_manifest.csv')) - 1}")
    for i in issues:
        print("ISSUE", i)
    print("GATE 4 PASS" if not issues else "GATE 4 FAIL")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
