from pathlib import Path
import sys
import io
import os
import zipfile
import tempfile

import streamlit as st

from codeinsight.pipeline.runner import run_pipeline


# Page setup
st.set_page_config(
    page_title="CodeInsight Mini",
    page_icon="🔍",
    layout="wide",
    menu_items={
    'Get Help': 'https://docs.streamlit.io',
    'Report a bug': "https://github.com/zeynep-dotcom/codeinsight-mini/issues",
    'About': "Code analysis tool"
    }
)

#2rem ~ 32px
st.markdown("""
<style>
/* subtle polish */
.block-container { padding-top: 2rem; } 
.small-muted { color: #6b7280; font-size: 0.9rem; }
.metric-wrap { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 14px; padding: 10px 16px; }
.section { padding: 8px 0 0; }
</style>
""", unsafe_allow_html=True)

# session state
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "zip_name" not in st.session_state:
    st.session_state.zip_name = None
if "report_format" not in st.session_state:
    st.session_state.report_format = "JSON"
if "agent_choice" not in st.session_state:
    st.session_state.agent_choice = "Ollama (local)"   # default

# Main
st.title("CodeInsight Mini")
st.caption("Advanced code analysis with AI integration")

# Sidebar
with st.sidebar:
    st.header("📁 Upload")
    zip_file = st.file_uploader("Upload a .zip of your code", type=["zip"], key="zip_uploader") # default widget
    file_valid = zip_file is not None and zip_file.size <= 200 * 1024 * 1024  # following size check ~
    if zip_file and not file_valid:
        st.error("File too large (max 200MB)")

    st.header("🤖 Agent")
    agent_choice = st.radio(
        "Choose an agent",
        ["Ollama (local)", "OpenAI", "No AI (raw results)"],
        index=["Ollama (local)", "OpenAI", "No AI (raw results)"].index(st.session_state.agent_choice),
        key="agent_choice",
        help="Ollama runs locally. OpenAI uses the OpenAI API. 'No AI' skips LLM suggestions."
    )

    run_clicked = st.button(
        "🚀 Run Analysis",
        use_container_width=True,
        disabled=(zip_file is None or not file_valid),
        key="run_btn"
    )

    st.markdown('<p class="small-muted">Limit 200MB • ZIP</p>', unsafe_allow_html=True) # HTML and (Default) Markdown p paragraph


# Helpers
def extract_zip(upload, dest: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(upload.getvalue())) as zf:
        for m in zf.infolist():
            name = m.filename.replace("\\", "/")
            if name.endswith("/"): # skip directories
                continue
            if name.startswith("/") or ".." in name.split("/"):
                continue # path traversal guard
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m, "r") as src, open(target, "wb") as dst:
                dst.write(src.read())
    return dest


def display_quality_score(result):
    """Display enhanced quality score with visual elements"""

    # enhanced_metrics = result.get("enhanced_metrics", {})
    # quality_score = enhanced_metrics.get("quality_score", 0)

    quality_score = int((result.get("enhanced_metrics") or {}).get("quality_score", 0))

    # Quality level determination
    if quality_score >= 85:
        quality_level = "Excellent"
        score_color = "#10b981"
    elif quality_score >= 70:
        quality_level = "Good"
        score_color = "#3b82f6"
    elif quality_score >= 55:
        quality_level = "Fair"
        score_color = "#f59e0b"
    else:
        quality_level = "Needs Improvement"
        score_color = "#ef4444"

    st.markdown(f"""
    <div class="quality-score">
        <h2 style="margin: 0; font-size: 2.5rem;">{quality_score}/100</h2>
        <p style="margin: 5px 0 0 0; font-size: 1.2rem; opacity: 0.9;">{quality_level}</p>
    </div>
    """, unsafe_allow_html=True)

def _plural(n: int) -> str:
    return "issue" if n == 1 else "issues"

def _short_name(p: str) -> str:
    return Path(p).name

# run on click
if run_clicked:
    try:
        # Map the selected UI label to a simple mode string the runner/agent can read.
        mode_map = {
            "Ollama (local)": "ollama",
            "OpenAI": "openai",
            "No AI (raw results)": "none",
        }
        os.environ["CODEINSIGHT_AGENT"] = mode_map.get(st.session_state.agent_choice, "ollama")

        with tempfile.TemporaryDirectory(prefix="cim_") as td:
            work = Path(td) / "code"
            work.mkdir(parents=True, exist_ok=True)
            extract_zip(zip_file, work)

            result = run_pipeline(work)

            # for selection
            st.session_state.analysis_result = result
            st.session_state.zip_name = zip_file.name

            # radon table (MI & CC avg)
            # st.subheader("Code complexity (Radon)")
            # if "radon" in result and result["radon"].get("files"):

    except zipfile.BadZipFile:
        st.error("The uploaded file is not a valid ZIP.")
    except FileNotFoundError as e:
        st.error(f"File not found: {e}")
    except PermissionError as e:
        st.error(f"Permission denied: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")

# render from session
result = st.session_state.analysis_result

if result is None:
    st.write("⬅️ Upload a ZIP in the sidebar and click **Run Analysis**.")
else:
    # show selected agent
    st.caption(f"Agent: **{st.session_state.agent_choice}**")

    # quality score for each file and the project
    display_quality_score(result)

    # summary section
    st.subheader("Summary")
    st.markdown('<div class="metric-wrap">', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.metric("Files scanned (.py)", result.get("files_scanned", 0))
    c2.metric("Issues found", result.get("issues_found", 0))
    st.markdown('</div>', unsafe_allow_html=True)

    issues = int(result.get("issues_found", 0))

    # success message
    def _plural(n: int) -> str:
        return "issue" if n == 1 else "issues"

    if issues == 0:
        st.success("✅ No issues found. Great job!")
    elif issues <= 5:
        st.info(f"✨ Good job! Only {issues} minor {_plural(issues)} found.")
    elif issues <= 20:
        st.warning(f"⚠️ {issues} {_plural(issues)} found. Consider reviewing them.")
    else:
        st.error(f"❌ {issues} {_plural(issues)} found. Code needs attention.")


    if result.get("summary"):
        st.caption(result["summary"])
    if result.get("adk_message"):
        st.info(f"ADK: {result['adk_message']}")


    # complexity (radon)
    # charts + lists
    st.divider()
    st.subheader("Maintainability & Complexity")

    radon_files = (result.get("radon", {}) or {}).get("files", [])
    if radon_files:
        mi_data = [{"path": f["path"], "MI": round(f["mi"], 1)} for f in radon_files]
        cc_data = [{"path": f["path"], "CC_avg": round(float(f["cc_avg"]), 1)} for f in radon_files]
        st.write("**Maintainability Index (MI)** — higher is better")
        # st.bar_chart({d["path"]: d["MI"] for d in mi_data}) # path
        st.bar_chart({Path(f["path"]).name: round(f["mi"], 1) for f in radon_files})  # or name
        st.write("**Average Cyclomatic complexity (CC_avg)** — lower is better")
        # st.bar_chart({d["path"]: d["CC_avg"] for d in cc_data}) # path
        st.bar_chart({Path(f["path"]).name: round(float(f["cc_avg"]), 1) for f in radon_files})  # or name

        radon_rows = [
            {"path": f["path"], "MI": round(f["mi"], 1), "CC_avg": round(f["cc_avg"], 1),
             "CC>10": sum(1 for i in f["cc_items"] if i["cc"] > 10)}
            for f in result["radon"]["files"]
            # or name
            # {
            # "file": Path(f["path"]).name,  # <= was "path": f["path"]
            # "MI": round(f["mi"], 1),
            # "CC_avg": round(float(f["cc_avg"]), 1),
            # "CC>10": sum(1 for i in f.get("cc_items", []) if i.get("cc", 0) > 10)
            #  }
            # for f in radon_files
        ]
        st.dataframe(radon_rows, use_container_width=True, hide_index=True)
        st.caption(
            f"Warnings: MI<65 → {result['radon']['summary']['mi_warnings']}, CC>10 blocks → {result['radon']['summary']['cc_hotspots']}")
    else:
        st.write("No Python files found for Radon.")

    # static analysis (pylint)
    st.subheader("Static analysis (Pylint)")
    if "pylint" in result:
        s = result["pylint"]["summary"]
        by_type_rows = [{"type": k, "count": v} for k, v in sorted(s.get("by_type", {}).items())]
        st.metric("Pylint messages (total)", s.get("total", 0))
        if by_type_rows:
            st.dataframe(by_type_rows, use_container_width=True, hide_index=True)
        with st.expander("View raw Pylint messages"):
            st.json(result["pylint"]["messages"])
    else:
        st.write("Pylint did not run.")

    # recommendations and ideas
    st.divider()
    st.subheader("File-based quality scores and recommendations")
    recs = result.get("recommendations") or {}
    rows = recs.get("files") or []
    if rows:
        st.dataframe(
            [{"file": _short_name(r["path"]), "Score": r["score"], "MI": r["mi"], "CC_avg": r["cc_avg"]} for r in rows],
            use_container_width=True, hide_index=True
        )
        with st.expander("Suggestions (per file)"):
            ideas_map = result.get("refactor_ideas") or {}
            for r in rows[:10]:
                st.markdown(f"**{_short_name(r['path'])}** — score: `{r['score']}`")
                for s in r.get("suggestions", []):
                    st.write(f"- {s}")
                for s in ideas_map.get(r["path"], []):
                    st.write(f"  • {s}")
                st.write("---")


    st.subheader("Project-level recommendations")
    for s in recs.get("project_suggestions", []):
        st.write(f"- {s}")

    # reports
    st.divider()
    st.subheader("Reports")

    paths = result.get("report_paths", {})
    fmt = st.radio("Choose report format:", ["JSON", "Markdown", "PDF"],
                   horizontal=True, key="report_format")

    if fmt == "JSON" and "json" in paths:
        try:
            with open(paths["json"], "r", encoding="utf-8") as f:
                st.download_button(
                    "⬇️ Download JSON report",
                    data=f.read(),
                    file_name=Path(paths["json"]).name,
                    mime="application/json",
                    key="dl_json",
                )
        except Exception as e:
            st.error(f"Could not read JSON report: {e}")

    elif fmt == "Markdown" and "markdown" in paths:
        try:
            with open(paths["markdown"], "r", encoding="utf-8") as f:
                content = f.read()
                st.download_button(
                    "⬇️ Download Markdown report",
                    data=content,
                    file_name=Path(paths["markdown"]).name,
                    mime="text/markdown",
                    key="dl_md",
                )
                with st.expander("Preview (Markdown)"):
                    st.markdown(content)
        except Exception as e:
            st.error(f"Could not read Markdown report: {e}")

    elif fmt == "PDF" and "pdf" in paths:
        try:
            with open(paths["pdf"], "rb") as f:
                st.download_button(
                    "⬇️ Download PDF report",
                    data=f.read(),
                    file_name=Path(paths["pdf"]).name,
                    mime="application/pdf",
                    key="dl_pdf",
                )
        except Exception as e:
            st.error(f"Could not read PDF report: {e}")

    # debug
    with st.expander("Raw result (debug)", expanded=False):
        st.json(result)