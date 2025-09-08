from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Iterable, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import os
import json

from codeinsight.analyzers.pylint_runner import run_pylint
from codeinsight.analyzers.radon_runner import run_radon
from codeinsight.agents.agent_factory import get_agent_from_env


"""adk imports with fallback so UI never crashes"""
USE_ADK: bool = (os.getenv("CODEINSIGHT_USE_ADK", "1") == "1")  # default ON
try:
    from google.adk import Agent  # noqa: F401 (import proves availability)
    from google.adk.flows.llm_flows.single_flow import SingleFlow
    ADK_OK = True
except Exception:
    SingleFlow = None  # type: ignore
    ADK_OK = False


# helpers
# def _avg(vals: List[float]) -> float:
#     return round(sum(vals) / len(vals), 2) if vals else 0.0

def _avg_mi(res: Dict) -> float:
    files = (res.get("radon", {}) or {}).get("files", [])
    if not files:
        return 0.0
    return round(sum(float(f["mi"]) for f in files) / len(files), 2)

def _avg_cc(res: Dict) -> float:
    files = (res.get("radon", {}) or {}).get("files", [])
    if not files:
        return 0.0
    return round(sum(float(f["cc_avg"]) for f in files) / len(files), 2)

def _pylint_total(res: Dict) -> int:
    return int(((res.get("pylint") or {}).get("summary") or {}).get("total", 0))

# computes file quality score
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, x))) # returns int

def _compute_quality_score(result: Dict[str, Any]) -> int:
    """
    Returns an integer quality score in [0, 100].
    Base:
      - avg MI from Radon (or 50.0 if unknown)
    Penalties (subtracted from base):
      - Pylint by_type counts (case-insensitive; accepts short/long keys):
          C=0.6, R=0.8, W=1.0, E=3.0, F=8.0
      - Radon summary:
          +2.0 per MI warning (files with MI < 65),
          +1.5 per CC hotspot (blocks with CC > 10)
      - Density (pylint messages per scanned file):
          if msgs/file > 3.0 → (per_file - 3.0) * 2.0
    Clamped to [0, 100].
    """
    radon = result.get("radon") or {}
    r_files = radon.get("files") or []

    # --- Base from MI ---
    if r_files:
        mi_vals = [float(f.get("mi", 0.0)) for f in r_files]
        avg_mi = sum(mi_vals) / max(1, len(mi_vals))
    else:
        avg_mi = 50.0  # neutral base if MI unknown

    # --- Pylint penalties (robust key normalization) ---
    by_type_raw = ((result.get("pylint") or {}).get("summary") or {}).get("by_type", {}) or {}
    def _pylint_counts(bt: Dict[str, Any]) -> Dict[str, int]:
        out = {"C": 0, "R": 0, "W": 0, "E": 0, "F": 0}
        for k, v in bt.items():
            try:
                n = int(v)
            except Exception:
                continue
            key = str(k).strip().lower()
            if key in ("c", "convention"):
                out["C"] += n
            elif key in ("r", "refactor"):
                out["R"] += n
            elif key in ("w", "warning"):
                out["W"] += n
            elif key in ("e", "error"):
                out["E"] += n
            elif key in ("f", "fatal"):
                out["F"] += n
        return out

    counts = _pylint_counts(by_type_raw)
    PYLINT_W = {"C": 0.6, "R": 0.8, "W": 1.0, "E": 3.0, "F": 8.0}
    pylint_penalty = sum(PYLINT_W[k] * counts[k] for k in counts)

    # --- Radon penalties ---
    rsum = (radon.get("summary") or {})
    mi_warn = int(rsum.get("mi_warnings", 0))
    cc_hot = int(rsum.get("cc_hotspots", 0))
    RADON_W_MI = 2.0   # per spec
    RADON_W_CC = 1.5   # per spec
    radon_penalty = RADON_W_MI * mi_warn + RADON_W_CC * cc_hot

    # --- Density penalty ---
    total_msgs = int(((result.get("pylint") or {}).get("summary") or {}).get("total", 0))
    files_scanned = (len(r_files) or int(rsum.get("files") or 1))
    per_file = total_msgs / max(1, files_scanned)
    DENSITY_THRESHOLD = 3.0
    DENSITY_SLOPE = 2.0
    density_penalty = (per_file - DENSITY_THRESHOLD) * DENSITY_SLOPE if per_file > DENSITY_THRESHOLD else 0.0

    # --- Final ---
    total_penalty = pylint_penalty + radon_penalty + density_penalty
    raw = avg_mi - total_penalty
    return _clamp(round(raw))  # assumes _clamp(x) -> int in [0,100]

# Workflow steps
def step_radon(ctx: dict) -> dict:
    agent = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 1: Radon")
    code_dir: Path = ctx["code_dir"]
    cfg = ctx.get("radon_config", {"complexity_threshold": 10, "maintainability_threshold": 65})
    ctx["radon"] = run_radon(code_dir, cfg)
    return ctx

def step_pylint(ctx: dict) -> dict:
    agent = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 2: Pylint")
    code_dir: Path = ctx["code_dir"]
    ctx["pylint"] = run_pylint(code_dir)
    return ctx

def step_llm_refactor(ctx):
    agent = ctx.get("agent")
    top_n = int(ctx.get("llm_top_n", 3))
    code_root = Path(ctx.get("code_dir", ""))

    # Get worst files by complexity
    radon_files = ctx.get("radon", {}).get("files", [])
    worst_files = sorted(radon_files,
                         key=lambda f: (-float(f.get("cc_avg", 0)), float(f.get("mi", 999))))[:top_n]

    def get_refactor_ideas(file_data):
        path, mi, cc_avg = file_data["path"], float(file_data.get("mi", 0)), float(file_data.get("cc_avg", 0))

        # Skip simple files
        if mi > 85.0 and cc_avg < 2.0:
            return ["No meaningful refactor; file is already simple. Consider adding CLI tests or docs."]

        # No agent fallback
        if not agent or not hasattr(agent, "generate"):
            return ["Split large functions into smaller helpers.",
                    "Simplify conditional branches; use early returns.",
                    "Extract repeated code into shared helpers."]

        # Build prompt with hotspots
        hotspots = [i for i in file_data.get("cc_items", []) if float(i.get("cc", 0)) > 10]
        hotspot_text = ", ".join(f"{i.get('name', '?')} (cc={i.get('cc')}) lines {i.get('line')}-{i.get('end')}"
                                 for i in hotspots) or "none"

        # Get code snippets for top 2 hotspots
        snippets = []
        if code_root.exists():
            try:
                file_text = (code_root / path).read_text(encoding="utf-8", errors="ignore")
                lines = file_text.splitlines()
                for i in sorted(hotspots, key=lambda x: float(x.get("cc", 0)), reverse=True)[:2]:
                    start, end = int(i.get("line", 1)) - 1, int(i.get("end", start + 20))
                    excerpt = "\n".join(lines[start:min(end, len(lines))])
                    if excerpt.strip():
                        snippets.append(f"# {i.get('name', '?')} (cc={i.get('cc')})\n```python\n{excerpt}\n```")
            except Exception:
                pass

        snippet_text = "\n\n".join(snippets) or "No code snippet available."

        prompt = f"""You are a senior Python code reviewer.\n
                ONLY use the provided code; do not invent functions/identifiers.
File: {path} | MI: {mi} | CC_avg: {cc_avg}
Hotspots: {hotspot_text}

{snippet_text}

Your task: Provide **3–5 specific and actionable refactoring suggestions**\n 
            - reference exact function/lines from the snippet,\n
            - say WHY (impact on readability/complexity/testability/perf),\n
            - keep it actionable (rename/extract/inline/guard/diff).\n
            If nothing actionable: return a single bullet "No meaningful refactor".
            as bullet points. Focus only on code improvements. 
            Do not ask questions. Do not request clarification. 
            Output only bullet points with clear suggestions."""

        try:
            response = agent.generate(prompt=prompt)
            bullets = [line.strip("-• ").strip() for line in response.splitlines() if line.strip()]
            return bullets[:5] if bullets else [response.strip()]
        except Exception:
            return ["LLM response could not be retrieved; showing static suggestions."]

    ctx["refactor_ideas"] = {f["path"]: get_refactor_ideas(f) for f in worst_files}
    return ctx

def step_merge(ctx: Dict[str, Any]) -> Dict[str, Any]:
    agent = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 3: Merge Results")

    radon = ctx["radon"]; pylint = ctx["pylint"]
    files = int((radon.get("summary") or {}).get("files", 0))
    mi_avg = _avg_mi({"radon": radon})
    cc_avg = _avg_cc({"radon": radon})
    pylint_total = int((pylint.get("summary") or {}).get("total", 0))

    issues_total = (
            pylint_total
            + int((radon.get("summary") or {}).get("mi_warnings", 0))
            + int((radon.get("summary") or {}).get("cc_hotspots", 0))
    )

    ctx["result"] = {
        "files_scanned": int(radon["summary"]["files"]),
        "issues_found": issues_total,
        "summary": "Pylint + Radon via ADK flow",
        "adk_message": "Workflow completed successfully",
        "pylint": pylint,
        "radon": radon,
        "refactor_ideas": ctx.get("refactor_ideas") or {},
    }
    return ctx

# comparison helpers
def _top_hotspots(res: Dict[str, Any], top: int = 5) -> List[Dict[str, Any]]:
    files = (res.get("radon") or {}).get("files") or []
    ranked = sorted(files, key=lambda f: (-float(f.get("cc_avg", 0.0)), float(f.get("mi", 999))))
    return [{"file": f["path"], "mi": round(float(f.get("mi",0)),1), "cc_avg": round(float(f.get("cc_avg",0)),1)} for f in ranked[:top]]

def build_compare_payload(res_a: Dict[str, Any], res_b: Dict[str, Any]) -> Dict[str, Any]:
    rows = [
        {"metric":"quality_score", "A":float(res_a.get("quality_score",0)), "B":float(res_b.get("quality_score",0))},
        {"metric":"issues_found",  "A":int(res_a.get("issues_found",0)),    "B":int(res_b.get("issues_found",0))},
        {"metric":"files_scanned", "A":int(res_a.get("files_scanned",0)),   "B":int(res_b.get("files_scanned",0))},
        {"metric":"pylint_total",  "A":_pylint_total(res_a),                "B":_pylint_total(res_b)},
        {"metric":"mi_avg",        "A":_avg_mi(res_a),                      "B":_avg_mi(res_b)},
        {"metric":"cc_avg",        "A":_avg_cc(res_a),                      "B":_avg_cc(res_b)},
    ]
    # delta + better
    better_high = {"quality_score","mi_avg"}
    for r in rows:
        r["delta"] = round(r["B"] - r["A"], 2)
        if r["A"] == r["B"]:
            r["better"] = "="
        elif r["metric"] in better_high:
            r["better"] = "A" if r["A"] > r["B"] else "B"
        else:
            r["better"] = "A" if r["A"] < r["B"] else "B"
    return {"metrics": rows, "top_hotspots": {"A": _top_hotspots(res_a), "B": _top_hotspots(res_b)}}

# Allows adk workflow to work with steps
def _build_adk_flow(steps: Iterable, agent: Any):
    """
    Created a SingleFlow across different ADK versions.
    some versions accept steps= in the constructor,
    others use processors=, or require add_step*/add_processor*.
    """
    # adapter that looks like an ADK "processor"
    class _FnProc:
        def __init__(self, fn): self.fn = fn
        def __call__(self, ctx): return self.fn(ctx)
        def process(self, ctx):   # some builds call .process()
            return self.fn(ctx)

    procs = [_FnProc(s) for s in steps]
    flow = SingleFlow()  # type: ignore[call-arg]

    # try common APIs in order
    if hasattr(flow, "add_steps"):
        flow.add_steps(list(steps))  # type: ignore[attr-defined]
        return flow
    if hasattr(flow, "add_step"):
        for s in steps:
            flow.add_step(s)  # type: ignore[attr-defined]
        return flow
    if hasattr(flow, "add_processors"):
        flow.add_processors(procs)  # type: ignore[attr-defined]
        return flow
    if hasattr(flow, "add_processor"):
        for p in procs:
            flow.add_processor(p)  # type: ignore[attr-defined]
        return flow

    # constructor styles (older builds)
    try:
        return SingleFlow(processors=procs)  # type: ignore[call-arg]
    except TypeError:
        try:
            return SingleFlow(steps=list(steps))  # type: ignore[call-arg]
        except TypeError:
            # Last resort: attach attribute that the engine might iterate
            setattr(flow, "processors", procs)
            return flow


# analyzes with adk workflow
def run_analysis_with_adk_flow(code_dir: Path, radon_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """always returns a JSON-friendly dict the UI understands"""
    code_dir = Path(code_dir)
    agent = get_agent_from_env()
    mode = (os.getenv("CODEINSIGHT_AGENT") or "ollama").lower()
    llm_enabled = mode != "none" and hasattr(agent, "generate")

    ctx: Dict[str, Any] = {
        "agent": agent,
        "code_dir": code_dir,
        "radon_config": radon_config or {"complexity_threshold": 10, "maintainability_threshold": 65},
        "llm_top_n": 3,
        "llm_enabled": llm_enabled,
    }

    steps = [step_radon, step_pylint, step_llm_refactor, step_merge]

    # Prefer ADK if requested and available
    if USE_ADK and ADK_OK and SingleFlow is not None:
        try:
            if hasattr(agent, "log"):
                agent.log("Building Google-ADK SingleFlow...")
            flow = _build_adk_flow(steps, agent)

            # Some builds expose run(ctx), others __call__(ctx)
            final_ctx = flow.run(ctx) if hasattr(flow, "run") else flow(ctx)  # type: ignore[misc]
            res = final_ctx.get("result", final_ctx)
            if isinstance(res, dict):
                res["adk_message"] = "Google-ADK SingleFlow active"
                return res
        except Exception as e:  # Fall through to manual pipeline
            if hasattr(agent, "log"):
                agent.log(f"ADK flow init failed ({e}); running manual pipeline.")

    # Manual pipeline (fallback or disabled)
    for step in steps:
        ctx = step(ctx)
    res = ctx["result"]
    if USE_ADK and not ADK_OK:
        res["adk_message"] = "Google-ADK not found; ran manual flow"
    elif not USE_ADK:
        res["adk_message"] = "ADK disabled; ran manual flow"
    return res

# provides llm comparison
def _get_agent():
    """Runs with chosen AI model"""
    try:
        from codeinsight.agents.agent_factory import get_agent_from_env
        return get_agent_from_env()
    except Exception:
        try:
            from google.adk import Agent
            return Agent(name="CodeInsight-Compare")
        except Exception:
            return None

def summarize_comparison_with_llm(res_a: dict, res_b: dict, cmp: dict) -> str:
    """
    Builds a compact markdown summary via the selected agent (Ollama/OpenAI),
    falling back to a templated string.
    """
    # Build a short, model-friendly prompt
    metrics = cmp.get("metrics", [])
    table = "\n".join(f"- {m['metric']}: A={m['A']} B={m['B']} Δ={m['delta']}" for m in metrics)
    prompt = (
        "You are a senior Python reviewer. Compare two Python projects.\n"
        "Be concise and actionable. Focus on maintainability and hotspots.\n"
        "Project with HIGHER quality score is BETTER project.\n"
        "Metrics:\n" + table + "\n\n"
        # "Write a short bullet list (5-8 bullets) of concrete, prioritized actions.\n"
        """Write a short Markdown brief that:
        1) Gives a one or two sentence executive summary of which project is healthier overall and why.
        2) Calls out where each project is stronger (higher maintainability better, lower complexity is better, issues).
        3) Recommends the **top 3 actions** to improve the weaker project (bullet list).
        4) Recommends the **top 3 actions** to improve the stronger project (bullet list)
        5) Do **not** include tables or code blocks. Keep under 280 words."""
    )

    agent = get_agent_from_env()
    if not agent:
        # non-LLM fallback
        bullets = [
            "Review modules with lowest MI and highest CC first.",
            "Address duplicated patterns and long functions.",
            "Fix Pylint warnings that indicate potential bugs.",
            "Add unit tests around complex branches.",
            "Document public APIs and clarify responsibilities.",
        ]
        return "\n".join(f"- {b}" for b in bullets)

    try:
        text = agent.generate(prompt=prompt)  # adapt to your agent interface
        return text.strip() or "_(empty LLM response)_"
    except Exception as e:
        return f"_(LLM error: {e})_"