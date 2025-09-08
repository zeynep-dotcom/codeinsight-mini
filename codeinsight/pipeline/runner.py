from __future__ import annotations
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor

import os

from codeinsight.agents.adk_flow_integration import run_analysis_with_adk_flow, _compute_quality_score
from codeinsight.reporting.json_report import (
    save_json_report,
    save_markdown_report,
    save_pdf_report,
    save_pair_reports,
)

#comparison utilities
def _avg(seq):
    return sum(seq) / len(seq) if seq else 0.0

def _radon_avgs(res: Dict[str, Any]) -> tuple[float, float]:
    files = (res.get("radon") or {}).get("files") or []
    mi_vals = [float(f.get("mi", 0.0)) for f in files]
    cc_vals = [float(f.get("cc_avg", 0.0)) for f in files]
    return (_avg(mi_vals), _avg(cc_vals))

def _pylint_total(res: Dict[str, Any]) -> int:
    return int(((res.get("pylint") or {}).get("summary") or {}).get("total", 0))

def _top_hotspots(res: Dict[str, Any], n: int = 5):
    files = (res.get("radon") or {}).get("files") or []
    files_sorted = sorted(files, key=lambda f: float(f.get("cc_avg", 0.0)), reverse=True)
    out = []
    for f in files_sorted[:n]:
        out.append({
            "file": Path(f.get("path", "")).name,
            "cc_avg": round(float(f.get("cc_avg", 0.0)), 1),
            "mi": round(float(f.get("mi", 0.0)), 1),
        })
    return out

def compare_results(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Build a JSON-friendly comparison snapshot."""
    mi_a, cc_a = _radon_avgs(a); mi_b, cc_b = _radon_avgs(b)
    rows = [
        {"metric": "quality_score", "A": float(a.get("quality_score", 0)), "B": float(b.get("quality_score", 0))},
        {"metric": "issues_found", "A": int(a.get("issues_found", 0)), "B": int(b.get("issues_found", 0))},
        {"metric": "files_scanned", "A": int(a.get("files_scanned", 0)), "B": int(b.get("files_scanned", 0))},
        {"metric": "pylint_total", "A": _pylint_total(a), "B": _pylint_total(b)},
        {"metric": "mi_avg", "A": round(mi_a, 1), "B": round(mi_b, 1)},
        {"metric": "cc_avg", "A": round(cc_a, 1), "B": round(cc_b, 1)},
    ]
    # who is “better”? (higher is better for score, mi; lower for issues, pylint, cc)
    better_high = {"quality_score", "mi_avg"}
    for r in rows:
        r["delta"] = round(float(r["B"]) - float(r["A"]), 2)
        if r["A"] == r["B"]:
            r["better"] = "="
        elif r["metric"] in better_high:
            r["better"] = "A" if r["A"] > r["B"] else "B"
        else:
            r["better"] = "A" if r["A"] < r["B"] else "B"

    return {
        "metrics": rows,
        "top_hotspots": {"A": _top_hotspots(a), "B": _top_hotspots(b)},
    }

def run_pair_and_compare(dir_a: Path, dir_b: Path, with_llm: bool = True):
    """Analyze dir_a and dir_b in parallel, then compare + LLM summary."""
    res_a, res_b = run_pipeline_pair(dir_a, dir_b)

    name_a = Path(dir_a).name
    name_b = Path(dir_b).name

    cmp = compare_results(res_a, res_b)

    llm_md = None
    if with_llm:
        try:
            # minimal fallback:
            from codeinsight.agents.adk_flow_integration import summarize_comparison_with_llm
            llm_md = summarize_comparison_with_llm(res_a, res_b, cmp)  # returns markdown
        except Exception as e:
            llm_md = f"_LLM comparison unavailable: {e}_"

    # Save dual reports in all formats that are supported
    reports_dir = Path("artifacts") / "reports"
    res_paths = {}
    for fmt in ("json", "markdown", "pdf"): # simple versions
        try:
            p = save_pair_reports((name_a, res_a),(name_b, res_b))
            res_paths[fmt] = str(p)
        except Exception as _:
            pass

    # Expose paths via compare payload so UI can offer a combined download if desired
    cmp["_report_paths"] = res_paths

    return res_a, res_b, cmp, llm_md

# Runs two analyses in parallel and return (resA, resB).
def run_pipeline_pair(dir_a: Path, dir_b: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(run_pipeline, dir_a)
        fb = ex.submit(run_pipeline, dir_b)
        res_a = fa.result()
        res_b = fb.result()
    return res_a, res_b

def run_pipeline(code_dir: Path) -> Dict[str, Any]:
    """
    radon -> pylint -> recommend/LLM -> merge (manual or adk workflow)
    quality score
    uses code_auditor _agent for an adk message
    """
    code_dir = Path(code_dir) # ensures the input is always Path
    result = run_analysis_with_adk_flow(code_dir)

    # defensive defaults
    result.setdefault("radon", {"summary": {"files": 0}, "files": []})
    result.setdefault("pylint", {"summary": {"total": 0}})
    result.setdefault("recommendations", {})

    # uses recommender first to compute and attach quality score
    qs = _compute_quality_score(result)
    result["enhanced_metrics"] = {"quality_score": qs}
    result["quality_score"] = qs

    # ensure there is an adk message (if message missing fall back to code_auditor_agent)
    mode = (os.getenv("CODEINSIGHT_AGENT") or "ollama").lower()
    label = {"ollama": "Ollama (local)", "openai": "OpenAI", "none": "No AI (raw results)"}.get(mode, mode)
    result.setdefault("adk_message", f"Agent: {label}")

    reports_dir = Path("artifacts/reports")
    json_path = save_json_report(result, reports_dir)
    md_path = save_markdown_report(result, reports_dir)
    pdf_path = save_pdf_report(result, reports_dir)

    result["report_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "pdf": str(pdf_path),
    }

    return result
