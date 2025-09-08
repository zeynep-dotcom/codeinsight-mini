from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Tuple

import datetime as dt
import json
import matplotlib.pyplot as plt

try:
    from fpdf import FPDF  # fpdf2
except Exception:  # PDF optional
    FPDF = None

# JSON
def save_json_report(data: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"report_{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

# Markdown
def save_markdown_report(result: dict, outdir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = outdir / f"report_{ts}.md"

    lines = []
    lines.append(f"# CodeInsight Report ({ts})\n")
    lines.append(f"**Files scanned:** {result.get('files_scanned',0)}")
    lines.append(f"**Issues found:** {result.get('issues_found',0)}")
    qs = result.get("enhanced_metrics", {}).get("quality_score", 0)
    lines.append(f"**Quality score:** {qs}/100\n")

    recs = (result.get("recommendations") or {}).get("project_suggestions", [])
    if recs:
        lines.append("## Project-level Suggestions")
        for r in recs:
            lines.append(f"- {r}")

    ideas = result.get("refactor_ideas", {})
    if ideas:
        lines.append("\n## Refactor Ideas (top_files)")
        for file, tips in ideas.items():
            lines.append(f"### {file}")
            for t in tips:
                lines.append(f"- {t}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path

# PDF (weasyprint didn't work)
def _save_chart_image(data: dict, title: str, outpath: Path):
    if not data:
        return None
    plt.figure(figsize=(6, 4))
    plt.bar(list(data.keys()), list(data.values()))
    plt.title(title)
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    return outpath

def _short(s: str, max_len: int = 160) -> str:
    s = str(s or "")
    return s if len(s) <= max_len else s[: max_len - 3] + "..."

def save_pdf_report(result: dict, outdir: Path) -> Path:
    # lazy import so the app still runs if fpdf2 is missing
    from fpdf import FPDF

    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = outdir / f"report_{ts}.pdf"

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)          # L, T, R
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ----- fonts -----
    font_dir = Path("codeinsight/assets/fonts")
    regular = font_dir / "DejaVuSans.ttf"
    bold    = font_dir / "DejaVuSans-Bold.ttf"
    if regular.exists():
        pdf.add_font("DejaVu", "",  str(regular), uni=True)
        if bold.exists():
            pdf.add_font("DejaVu", "B", str(bold), uni=True)
            bold_style = "B"
        else:
            bold_style = ""  # fall back to regular if bold TTF missing
        font_name = "DejaVu"
    else:
        font_name = "Helvetica"
        bold_style = "B"  # built-in Helvetica has bold

    def set_regular(sz): pdf.set_font(font_name, "", sz)
    def set_bold(sz):    pdf.set_font(font_name, bold_style, sz)

    # always compute the actual writable width
    def w_available() -> float:
        return pdf.w - pdf.l_margin - pdf.r_margin

    # helper that safely writes long text
    def write_line(txt: str, h: float = 8):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w_available(), h, txt)

    # ----- title -----
    set_regular(14)
    pdf.cell(0, 10, f"CodeInsight Report ({ts})", ln=True, align="C")
    pdf.ln(4)

    # ----- summary -----
    set_regular(11)
    write_line(f"Files scanned: {result.get('files_scanned', 0)}")
    write_line(f"Issues found: {result.get('issues_found', 0)}")
    qs = (result.get("enhanced_metrics") or {}).get("quality_score", 0)
    write_line(f"Quality score: {qs}/100")

    # ----- charts -----
    radon_files = (result.get("radon") or {}).get("files", [])
    if radon_files:
        mi_data = {Path(f["path"]).name: round(float(f["mi"]), 1) for f in radon_files}
        cc_data = {Path(f["path"]).name: round(float(f["cc_avg"]), 1) for f in radon_files}

        mi_chart = outdir / f"mi_chart_{ts}.png"
        cc_chart = outdir / f"cc_chart_{ts}.png"
        _save_chart_image(mi_data, "Maintainability Index (higher is better)", mi_chart)
        _save_chart_image(cc_data, "Cyclomatic Complexity (lower is better)", cc_chart)

        pdf.ln(6)
        set_bold(12)
        pdf.cell(0, 10, "Charts", ln=True)

        # Always position images at left margin and use available width
        x = pdf.l_margin
        w = w_available()
        if mi_chart.exists():
            pdf.image(str(mi_chart), x=x, w=w)
            pdf.ln(3)
        if cc_chart.exists():
            pdf.image(str(cc_chart), x=x, w=w)
            pdf.ln(3)

    # ----- project-level suggestions -----
    pdf.ln(6)
    set_bold(12)
    pdf.cell(0, 10, "Project-level Suggestions", ln=True)
    set_regular(11)
    for r in (result.get("recommendations") or {}).get("project_suggestions", []):
        write_line(f"- {_short(r)}")

    # ----- refactor ideas -----
    pdf.ln(4)
    set_bold(12)
    pdf.cell(0, 10, "Refactor Ideas (Top Files)", ln=True)
    set_regular(11)
    for file, tips in (result.get("refactor_ideas") or {}).items():
        write_line(Path(file).name + ":")
        for t in tips:
            write_line(f"- {_short(t)}")

    pdf.output(str(path))
    return path

def to_json_bytes(data: dict) -> bytes:
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

def save_pair_reports(
    a: Tuple[str, Dict[str, Any]],
    b: Tuple[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Parameters:
      a: (project_name, report_data)
      b: (project_name, report_data)
    Job:
      - json_report.save_json_report
      - json_report.save_markdown_report
      - json_report.save_pdf_report
    for BOTH of the projects.
    Save path:
      reports/<YYYYmmdd-HHMMSS>_<A>_vs_<B>/{A,B}/
    Feedback:
      {
        "root": "<kök_klasör>",
        "A": {"name": "<A>", "created": {...}, "errors": {...?}},
        "B": {"name": "<B>", "created": {...}, "errors": {...?}}
      }
    """
    name_a, data_a = a
    name_b, data_b = b

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path("reports") / f"{ts}_{name_a}_vs_{name_b}"
    out_a = root / name_a
    out_b = root / name_b
    out_a.mkdir(parents=True, exist_ok=True)
    out_b.mkdir(parents=True, exist_ok=True)

    def save_all_for_one(proj_name: str, report_data: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
        created, errors = {}, {}
        tasks = [
            ("json", "json", save_json_report),
            ("markdown", "md", save_markdown_report),
            ("pdf", "pdf", save_pdf_report),
        ]
        for key, ext, func in tasks:
            try:
                path = func(report_data, str(outdir))
                if not path:
                    path = outdir / f"{proj_name}.{ext}"
                created[key] = str(path)
            except TypeError:
                try:
                    default_path = outdir / f"{proj_name}.{ext}"
                    path = func(report_data, str(default_path))
                    created[key] = str(path) if path else str(default_path)
                except Exception as e:
                    errors[key] = f"{type(e).__name__}: {e}"
            except Exception as e:
                errors[key] = f"{type(e).__name__}: {e}"
        return {"created": created, **({"errors": errors} if errors else {})}

    resA = save_all_for_one(name_a, data_a, out_a)
    resB = save_all_for_one(name_b, data_b, out_b)

    return {"root": str(root), "A": {"name": name_a, **resA}, "B": {"name": name_b, **resB}}
