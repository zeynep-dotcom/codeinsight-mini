from __future__ import annotations
from pathlib import Path
from statistics import mean
from typing import Any, Dict

import os

from codeinsight.agents.adk_flow_integration import run_analysis_with_adk_flow
from codeinsight.reporting.json_report import (
    save_json_report,
    save_markdown_report,
    save_pdf_report,
)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, x))) # returns int

def _compute_quality_score(result: Dict[str, Any]) -> int:
    """
    per-file scores from recommendations, returns an integer 0-100.
    (below is an explanation of how calculation works for this project)
    Heuristic:
    - Base is average Maintainability Index (MI).
    - Subtract weighted penalties:
        Pylint: C=0.6, R=0.8, W=1.0, E=3.0, F=8.0
        Radon:  +2.0 per MI warning (files with MI<65)
                +1.5 per CC hotspot (blocks with CC>10)
        Density: if total findings per file > 3, extra 2 points per excess unit
    Clamp to [0, 100].
    """

    # -----OLD-----
    # if recommender exists -> average file scores
    # files = (result.get("recommendations") or {}).get("files", [])
    # if files:
    #     try:
    #         return _clamp(round(mean(f.get("score", 0) for f in files)))
    #     except Exception:
    #         pass  # fall back below if something is off
    #
    # # fallback -> mi average minus penalty for pylint messages
    # radon = result.get("radon") or {}
    # radon_files = radon.get("files") or []
    # mi_avg = mean([f.get("mi", 100.0) for f in radon_files]) if radon_files else 100.0
    #
    # pylint_total = int((result.get("pylint") or {}).get("summary", {}).get("total", 0))
    # penalty = min(40.0, pylint_total * 1.5)  # tune later
    #
    # return _clamp(round(mi_avg - penalty))

    radon = result.get("radon") or {}
    r_files = radon.get("files") or []

    # base from MI
    if r_files:
        avg_mi = sum(float(f.get("mi", 0.0)) for f in r_files) / max(1, len(r_files))
    else:
        avg_mi = 50.0  # neutral base if MI unknown

    # pylint penalties
    PYLINT_W = {"C": 0.30, "R": 0.50, "W": 0.80, "E": 2.20, "F": 5.50}
    by_type = ((result.get("pylint") or {}).get("summary") or {}).get("by_type", {}) or {}
    norm = {k.upper(): int(v) for k, v in by_type.items()}
    # also accept long keys
    long2short = {"convention": "C", "refactor": "R", "warning": "W", "error": "E", "fatal": "F"}
    for long_k, short_k in long2short.items():
        if long_k in by_type:
            norm[short_k] = int(by_type[long_k])

    C = norm.get("C", 0)
    R = norm.get("R", 0)
    W = norm.get("W", 0)
    E = norm.get("E", 0)
    F = norm.get("F", 0)
    pylint_penalty = (
            PYLINT_W["C"] * C +
            PYLINT_W["R"] * R +
            PYLINT_W["W"] * W +
            PYLINT_W["E"] * E +
            PYLINT_W["F"] * F
    )

    # radon penalties
    RADON_W_MI = 1.20  # files with MI < 65
    RADON_W_CC = 0.90  # CC > 10 blocks
    rsum = (radon.get("summary") or {})
    mi_warn = int(rsum.get("mi_warnings", 0))
    cc_hot = int(rsum.get("cc_hotspots", 0))
    radon_penalty = RADON_W_MI * mi_warn + RADON_W_CC * cc_hot

    # density penalty (messages per file)
    total_msgs = int(((result.get("pylint") or {}).get("summary") or {}).get("total", 0))
    files_scanned = int((rsum.get("files") or len(r_files) or 1))
    per_file = total_msgs / max(1, files_scanned)
    DENSITY_THRESHOLD = 4.0
    DENSITY_SLOPE = 1.2
    density_penalty = (per_file - DENSITY_THRESHOLD) * DENSITY_SLOPE if per_file > DENSITY_THRESHOLD else 0.0

    PENALTY_SCALE = 0.85
    total_penalty = PENALTY_SCALE * (pylint_penalty + radon_penalty + density_penalty)
    raw = avg_mi - total_penalty
    return _clamp(round(raw))


def run_pipeline(code_dir: Path) -> Dict[str, Any]:
    """
    radon -> pylint -> recommend/LLM -> merge (manual workflow)
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
    result["enhanced_metrics"] = {
        "quality_score": _compute_quality_score(result)
    }

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