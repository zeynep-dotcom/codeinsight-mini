from __future__ import annotations
from typing import Any, Dict, List

def score_file(mi: float, cc_avg: float) -> float:
    mi_part = max(0.0, min(100.0, mi))
    cc_penalty = min(40.0, max(0.0, (cc_avg - 5) * 6))
    return round(mi_part - cc_penalty, 1)

def recommend_for_file(f: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    mi = f.get("mi", 100.0)
    cc_items = f.get("cc_items", [])
    hot = [i for i in cc_items if i.get("cc", 0) > 10]
    if mi < 65:
        recs.append("MI<65 — split large functions, remove duplicates, and refactor into smaller helpers.")
    if hot:
        w = max(cc_items, key=lambda i: i.get("cc", 0))
        recs.append(f"High complexity: `{w['name']}` {w['line']}-{w['end']} (CC={w['cc']}). Simplify conditions.")
    return recs


def aggregate_pylint_topics(msgs: List[Dict[str, Any]]) -> List[str]:
    if not msgs: return []
    by = {}
    for m in msgs:
        sym = m.get("symbol") or m.get("message-id") or "unknown"
        by[sym] = by.get(sym, 0) + 1

    out: List[str] = []

    def add(sym, text):
        if by.get(sym): out.append(f"{text} ({by[sym]} kez).")

    add("unused-import", "Remove unused imports")
    add("wildcard-import", "Use specific imports instead of `from x import *`")
    add("undefined-variable", "Undefined variable usage found; check names and scope")
    add("eval-used", "Use of `eval` is risky — prefer safer alternatives")
    add("bad-indentation", "Fix indentation (use 4 spaces, avoid tabs)")
    add("redefined-builtin", "Do not shadow built-in names (e.g. `list`)")
    return out


def build_recommendations(analysis: Dict[str, Any]) -> Dict[str, Any]:
    radon_files = (analysis.get("radon", {}).get("files")) or []
    pylint_msgs = (analysis.get("pylint", {}).get("messages")) or []

    files = [{
        "path": f["path"],
        "mi": round(f.get("mi", 0.0), 1),
        "cc_avg": round(float(f.get("cc_avg", 0.0)), 1),
        "score": score_file(f.get("mi", 100.0), float(f.get("cc_avg", 0.0))),
        "suggestions": recommend_for_file(f),
        "cc_items": f.get("cc_items", []),
    } for f in radon_files]

    files.sort(key=lambda r: r["score"])  # worst first

    proj = []
    rsum = analysis.get("radon", {}).get("summary", {})
    if rsum.get("mi_warnings", 0) > 0:
        proj.append("Files with MI<65 detected — consider modularization and simplification.")
    if rsum.get("cc_hotspots", 0) > 0:
        proj.append("Functions with CC>10 detected — reduce complex branching.")
    proj += aggregate_pylint_topics(pylint_msgs)

    return {"files": files, "project_suggestions": proj}