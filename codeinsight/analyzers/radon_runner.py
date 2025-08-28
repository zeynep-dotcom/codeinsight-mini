from __future__ import annotations
from pathlib import Path
from radon.complexity import cc_visit
from radon.metrics import mi_visit

def calculate_average_complexity(cc_blocks):
    if not cc_blocks:
        return 0.0
    total_complexity = sum(block.complexity for block in cc_blocks)
    return total_complexity / len(cc_blocks)

def analyze_file(path: Path,  config: dict | None = None) -> dict:
    code = path.read_text(encoding="utf-8", errors="ignore")
    cc_blocks = cc_visit(code) # items
    mi = float(mi_visit(code, multi=False))  # better>65
    return {
        "path": str(path),
        "mi": mi,
        "cc_items": [
            {"name": b.name, "line": b.lineno, "end": b.endline, "cc": int(b.complexity)}
            for b in cc_blocks
        ],
        "cc_avg": calculate_average_complexity(cc_blocks),
    }

def run_radon(code_dir: Path, config: dict | None = None) -> dict:
    code_dir = Path(code_dir)

    config = config or {}
    complexity_threshold = int(config.get("complexity_threshold", 10))
    maintainability_threshold = int(config.get("maintainability_threshold", 65))

    per_file = []
    for p in code_dir.rglob("*.py"):
        # analyze_file should also accept thresholds or read them here
        res = analyze_file(p, {
            "complexity_threshold": complexity_threshold,
            "maintainability_threshold": maintainability_threshold,
        })
        per_file.append(res)

    # later tune thresholds (?)
    mi_warn = sum(1 for f in per_file if f.get("mi", 100) < maintainability_threshold)
    cc_hot = sum(
        sum(1 for i in f.get("cc_items", []) if i.get("cc", 0) > complexity_threshold)
        for f in per_file
    )

    return { # improve
        "summary": {
            "files": len(per_file),
            "mi_warnings": int(mi_warn),
            "cc_hotspots": int(cc_hot),
        },
        "files": per_file,
    }

