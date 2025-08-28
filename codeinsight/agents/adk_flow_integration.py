from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import os

from codeinsight.analyzers.pylint_runner import run_pylint
from codeinsight.analyzers.radon_runner import run_radon
from codeinsight.recommend.recommender import build_recommendations
from codeinsight.agents.agent_factory import get_agent_from_env


"""adk imports with fallback so UI never crashes"""
try:
    from google.adk import Agent
    from google.adk.flows.llm_flows.single_flow import SingleFlow
except Exception:
    Agent = None
    SingleFlow = None

from codeinsight.agents.ollama_agent import OllamaAgent

def _build_agent():
    # local LLM
    return OllamaAgent(model="llama3.1:8b")

# Workflow steps
"""pure functions over a context dict"""
def step_radon(ctx: Dict[str, Any]) -> Dict[str, Any]:
    agent: Any = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 1: Radon")
    code_dir: Path = ctx["code_dir"]
    cfg = ctx.get("radon_config", {"complexity_threshold": 10, "maintainability_threshold": 65})
    ctx["radon"] = run_radon(code_dir, cfg)
    return ctx

def step_pylint(ctx: Dict[str, Any]) -> Dict[str, Any]:
    agent: Any = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 2: Pylint")
    code_dir: Path = ctx["code_dir"]
    ctx["pylint"] = run_pylint(code_dir)
    return ctx

# recommendations
def step_recommend(ctx):
    # build scores & rule-based suggestions
    ctx["recommendations"] = build_recommendations({
        "radon": ctx["radon"],
        "pylint": ctx["pylint"],
    })
    return ctx

def step_llm_refactor(ctx):
    agent = ctx.get("agent")
    rec = ctx.get("recommendations", {})
    files = rec.get("files", [])[:5]  # top 5 worst (might add configurable top n)

    ideas_map = {}
    for f in files:
        # agent's initial prompt
        prompt = (
                "You are a senior Python code reviewer.\n"
                f"File: {f['path']}\n"
                f"Maintainability Index (MI): {f['mi']}\n"
                f"Cyclomatic Complexity average (CC_avg): {f['cc_avg']}\n"
                "Hotspots: " + (", ".join(
            f"{i['name']} (cc={i.get('cc', 0)}) lines {i['line']}-{i['end']}"
            for i in (f.get('cc_items') or []) if i.get('cc', 0) > 10
        ) or "none") +
                "\n\nYour task: Provide **3–5 specific and actionable refactoring suggestions** "
                "as bullet points. Focus only on code improvements. "
                "Do not ask questions. Do not request clarification. "
                "Output only bullet points with clear suggestions."
        )
        # graceful fallback if no LLM
        if not agent or not hasattr(agent, "generate"):
            ideas_map[f["path"]] = [
                "Split large functions into smaller helpers.",
                "Simplify conditional branches; use early returns (guards).",
                "Extract repeated code into a shared helper function."
            ]
            continue
        try:
            text = agent.generate(prompt=prompt)  # adapt to your ADK API if different
            bullets = [x.strip("-• ").strip() for x in text.splitlines() if x.strip()]
            ideas_map[f["path"]] = bullets[:5] or [text.strip()]
        except Exception:
            ideas_map[f["path"]] = ["LLM response could not be retrieved; showing static suggestions."]

    ctx["refactor_ideas"] = ideas_map
    return ctx

def step_merge(ctx: Dict[str, Any]) -> Dict[str, Any]:
    agent = ctx.get("agent")
    if agent and hasattr(agent, "log"):
        agent.log("Step 3: Merge Results")

    radon = ctx["radon"]
    pylint = ctx["pylint"]
    rsum = (radon.get("summary") or {})

    files_scanned = int(rsum.get("files", 0))
    total = int((pylint.get("summary") or {}).get("total", 0)) \
            + int(rsum.get("mi_warnings", 0)) \
            + int(rsum.get("cc_hotspots", 0))

    ctx["result"] = {
        "files_scanned": int(radon["summary"]["files"]),
        "issues_found": total,
        "summary": "Pylint + Radon via ADK flow",
        "adk_message": "Workflow completed successfully",
        "pylint": pylint,
        "radon": radon,
        "recommendations": ctx.get("recommendations"),
        "refactor_ideas": ctx.get("refactor_ideas"),
    }

    return ctx

def run_analysis_with_adk_flow(code_dir: Path, radon_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """always returns a JSON-friendly dict the UI understands"""
    code_dir = Path(code_dir)

    # fallback if ADK or SingleFlow isn’t importable run steps sequentially
    # if not Agent or not SingleFlow:
    #     radon = run_radon(code_dir, radon_config or {})
    #     pylint = run_pylint(code_dir)
    #     total = (int(pylint["summary"]["total"]),
    #              + int(radon["summary"]["mi_warnings"]),
    #              + int(radon["summary"]["cc_hotspots"]))
    #     return {
    #         "files_scanned": int(radon["summary"]["files"]),
    #         "issues_found": total,
    #         "summary": "Pylint + Radon (ADK not available; ran without flow).",
    #         "adk_message": None,
    #         "pylint": pylint,
    #         "radon": radon,
    #     }
    #
    # # adk manual flow path
    # agent = _build_agent()
    # ctx: Dict[str, Any] = {
    #     "agent": agent,
    #     "code_dir": code_dir,
    #     "radon_config": radon_config or {"complexity_threshold": 10, "maintainability_threshold": 65},
    #     "llm_top_n": 5,
    #     "llm_enabled": True,
    # }
    #
    # steps = [step_radon, step_pylint, step_recommend, step_llm_refactor, step_merge]
    # for step in steps:
    #     ctx = step(ctx)
    #
    # return ctx["result"]

    agent = get_agent_from_env()
    mode = (os.getenv("CODEINSIGHT_AGENT") or "ollama").lower()
    llm_enabled = mode != "none" and hasattr(agent, "generate")

    ctx: Dict[str, Any] = {
        "agent": agent,
        "code_dir": code_dir,
        "radon_config": radon_config or {"complexity_threshold": 10, "maintainability_threshold": 65},
        "llm_top_n": 5,
        "llm_enabled": llm_enabled,
    }

    # Manual flow is simpler and works without ADK installed
    for step in (step_radon, step_pylint, step_recommend, step_llm_refactor, step_merge):
        ctx = step(ctx)

    # Friendly agent label for the UI
    label = {"ollama": "Ollama (local)", "openai": "OpenAI", "none": "No AI (raw results)"}.get(mode, mode)
    res = ctx["result"]
    res.setdefault("adk_message", f"Agent: {label}")
    return res