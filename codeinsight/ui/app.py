from pathlib import Path
import io
import os
import zipfile
import tempfile

import altair as alt
import pandas as pd
import streamlit as st

from codeinsight.pipeline.runner import run_pair_and_compare
from codeinsight.reporting.json_report import save_pair_reports

# Page setup
st.set_page_config(
    page_title="CodeInsight Mini",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
    'Get Help': 'https://docs.streamlit.io',
    'Report a bug': "https://github.com/zeynep-dotcom/codeinsight-mini/issues",
    'About': "Code analysis tool"
    }
)

#2rem ~ 32px
st.markdown(
    """
<style>
:root{
    /* Light theme tokens */
    --ink: #111827;        /* main text */
    --border: #43436a;     /* borders */
    --accent-ink: #fff; /* text on accent */
# }

/* Page background + base text*/
html, body{
    .stApp {
    background: linear-gradient(180deg, #d3bce0 0%, #f2d1bb 50%, #d0c7eb 100%);
    color: #362c57
    }

/* Layout spacing + header line removal*/
.block-container { padding-top: 1.2rem; }
header[data-testid="stHeader"] { background: transparent; box-shadow: none; }

/* Sidebar background */
[data-testid=stSidebar] {
        background: linear-gradient(180deg, #ede4f2 0%, #f2e4da 50%, #e8eafa 100%);
}

/* Scope to main content so the sidebar/root never match */
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stMarkdownContainer"]:first-child > .glass-anchor){
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 16px;
  padding: 16px 18px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 10px 30px rgba(0,0,0,.25);
  margin-bottom: 16px;
}

/* optional: tidy headings inside glass cards */
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stMarkdownContainer"]:first-child > .glass-anchor) h2,
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stMarkdownContainer"]:first-child > .glass-anchor) h3{
  margin-top: .25rem;
}

/* Buttons (Run Analysis, etc.) */
[data-testid="stButton"] > button {
  background: #f97316;           /* base color */
  color: #ffffff;
  border: 1px solid #EA580C;
  box-shadow: 0 8px 16px rgba(249,115,22,.20);
}
[data-testid="stButton"] > button:hover {
  background: #db6714;           /* hover */
  border-color: #db6714;
}
[data-testid="stButton"] > button:focus { outline: none; }

/* Download buttons */
/* All st.download_button buttons */
[data-testid="stDownloadButton"] > button {
  background: #f97316;           /* base color */
  color: #FFFFFF;
  border: 1px solid #EA580C;
  box-shadow: 0 8px 16px rgba(249,115,22,.20);
}
[data-testid="stDownloadButton"] > button:hover {
  background: #db6714;           /* hover */
  border-color: #db6714;
}
[data-testid="stDownloadButton"] > button:focus { outline: none; }

/* Inputs / selects */
[data-baseweb="input"]>div, 
[data-baseweb="select"]>div {
  background: ##dfd5e0 !important;
  color: var(--ink) !important;
  border: 1px solid var(--border) !important;
}

/* Dropdown menu (Agent / Model) */
div[role="listbox"]{
  background: #fff !important;
  color: var(--ink) !important;#506994
  border: 1px solid var(--border) !important;
  box-shadow: 0 12px 24px rgba(0,0,0,0.08) !important;
}
div[role="listbox"] [role="option"]{ color: var(--ink) !important; }
div[role="listbox"] [role="option"]:hover{ background:#f3f4f6 !important; }
div[role="listbox"] [role="option"][aria-selected="true"]{ background:#fef9c3 !important; }

/* Toggle (Use ADK) */
[data-testid="stToggle"] [data-baseweb="switch"] > label > div {
  background: #e5e7eb !important; border: 1px solid var(--border) !important;
}
[data-testid="stToggle"] [data-baseweb="switch"] > label > input:checked + div {
  background: var(--accent) !important; border-color: #fbbf24 !important;
}
[data-testid="stToggle"] [data-baseweb="switch"] > label > div > div { background: #ffffff !important; }

/* DataFrame (AG Grid) */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  overflow: hidden;
}
[data-testid="stDataFrame"] .ag-header,
[data-testid="stDataFrame"] .ag-header-cell,
[data-testid="stDataFrame"] .ag-header-cell-text {
  background: #f8fafc !important;
  color: var(--ink) !important;
  border-color: #e5e7eb !important;
}
[data-testid="stDataFrame"] .ag-root-wrapper,
[data-testid="stDataFrame"] .ag-root,
[data-testid="stDataFrame"] .ag-center-cols-container,
[data-testid="stDataFrame"] .ag-row,
[data-testid="stDataFrame"] .ag-cell {
  background: #ffffff !important;
  color: var(--ink) !important;
  border-color: #e5e7eb !important;
}
[data-testid="stDataFrame"] .ag-row-odd .ag-cell { background: #fafafa !important; }
[data-testid="stDataFrame"] .ag-row-hover .ag-cell,
[data-testid="stDataFrame"] .ag-row.ag-row-focus .ag-cell {
  background: #fff7cc !important; 
}


--grad-1:#1a1530;  --grad-2:#2a1f3d;
  --glass-bg:rgba(255,255,255,.08);
  --glass-border:rgba(255,255,255,.15);
  --widget-bg:rgba(255,255,255,.06);
  --widget-border:rgba(255,255,255,.18);
  --ink:#e5e7eb;
}

/* Use the tokens everywhere */
.stApp{ background: linear-gradient(180deg,var(--grad-1),var(--grad-2)); color: var(--ink); }
[data-testid="stSidebar"]{ background: linear-gradient(180deg,var(--grad-1),var(--grad-2)); }

div[data-testid="stFileUploaderDropzone"]{
  background: var(--widget-bg); border: 1px dashed var(--glass-border); border-radius:12px;
}

div[data-testid="stCodeBlock"]{
  background: var(--glass-bg) !important; border:1px solid var(--glass-border) !important;
  border-radius:14px !important; padding:12px 14px !important;
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
</style>
""",
    unsafe_allow_html=True,)



st.markdown("""
<style>
/* === Glass card for containers that have an anchor in their first child block === */
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stVerticalBlock"] .glass-anchor),
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stVerticalBlock"] > [data-testid="stMarkdownContainer"] .glass-anchor) {
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 16px;
  padding: 16px 18px;
  margin: 0 0 16px 0;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 10px 30px rgba(0,0,0,.25);
}

/* tidy headings inside card */
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stVerticalBlock"] .glass-anchor) h2,
.stMain [data-testid="stVerticalBlock"]
  :has(> [data-testid="stVerticalBlock"] .glass-anchor) h3{
  margin-top:.25rem;
}
</style>
""", unsafe_allow_html=True)

# invincible anchor
st.markdown('<a id="page-top"></a>', unsafe_allow_html=True)

# when div used visible empty row / pill
def glass_anchor(): st.markdown('<span class="glass-anchor"></span>', unsafe_allow_html=True)

# session state
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "zip_name" not in st.session_state:
    st.session_state.zip_name = None
if "report_format" not in st.session_state:
    st.session_state.report_format = "JSON"
if "agent_choice" not in st.session_state:
    st.session_state.agent_choice = "Ollama (local)"   # default
if "model_value" not in st.session_state:
    st.session_state.model_value = "llama3.1:8b" # safe default

with st.sidebar:
    agent_choice = st.selectbox(
        "Agent",
        ["Ollama (local)", "OpenAI", "No AI (raw results)"],
        index=["Ollama (local)", "OpenAI", "No AI (raw results)"].index(st.session_state.agent_choice),
        key="agent_choice",
        help="Ollama runs locally. OpenAI uses the OpenAI API. 'No AI' skips LLM suggestions."
    )
    # Model field adapts to agent choice
    placeholder = "llama3.1:8b" if agent_choice == "Ollama (local)" else "gpt-4o-mini"
    model_value = st.text_input("Model", value=st.session_state.model_value or placeholder, key="model_value")
    # adk toggle
    use_adk = st.toggle("Use ADK", value=True, key="use_adk")
    with st.container():
        glass_anchor()
        st.markdown("""
            Quick guide
            - **Upload** two `.zip` projects (≤200 MB).
            - **Run** **Dual Analysis**.
            - **Review**: LLM comparison, refactor ideas, metrics.
            - **Tweak**: change **Agent/Model** or **Use ADK**, then **Rerun**.
        
            **Tip:** Zip only code (exclude `.venv`, `__pycache__`, large data). Remove a file with **×**.
        """)


# Title
st.title("CodeInsight Mini")
st.caption("Advanced code analysis and project quality comparison with AI integration")

st.markdown('<div class="toolbar">', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# Apply environment for pipeline/agents
os.environ["CODEINSIGHT_USE_ADK"] = "1" if use_adk else "0"
if agent_choice == "Ollama (local)":
    os.environ["CODEINSIGHT_AGENT"] = "ollama"
    if model_value:
        os.environ["CODEINSIGHT_OLLAMA_MODEL"] = model_value
    os.environ.setdefault("CODEINSIGHT_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
elif agent_choice == "OpenAI":
    os.environ["CODEINSIGHT_AGENT"] = "openai"
    if model_value:
        os.environ["OPENAI_MODEL"] = model_value
else:
    os.environ["CODEINSIGHT_AGENT"] = "none"


# dual upload
st.markdown("### Analyze and compare two projects")

u1, u2 = st.columns(2)
with u1:
    zip_a = st.file_uploader("First Project(.zip)", type=["zip"], key="zipA")
with u2:
    zip_b = st.file_uploader("Second Project (.zip)", type=["zip"], key="zipB")

run_dual = st.button("Run Dual Analysis", disabled=not (zip_a and zip_b))


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

def _analyze_zip_pair(zip_a, zip_b):
    with tempfile.TemporaryDirectory(prefix="cim_dual_") as td:
        dir_a = Path(td) / zip_a.name
        dir_b = Path(td) / zip_b.name
        dir_a.mkdir(parents=True, exist_ok=True)
        dir_b.mkdir(parents=True, exist_ok=True)
        extract_zip(zip_a, dir_a)
        extract_zip(zip_b, dir_b)

        res_a, res_b, cmp_payload, llm_md = run_pair_and_compare(dir_a, dir_b, with_llm=True)
        return res_a, res_b, cmp_payload, llm_md

if run_dual:
    with st.spinner("Analyzing both projects in parallel…"):
        res_a, res_b, cmp, llm_md = _analyze_zip_pair(zip_a, zip_b)
        st.session_state["dual_A"] = res_a
        st.session_state["dual_B"] = res_b
        st.session_state["dual_cmp"] = cmp
        st.session_state["dual_cmp_llm"] = llm_md
    st.session_state["dual_A"] = res_a
    st.session_state["dual_B"] = res_b
    st.session_state["dual_cmp"] = cmp

if st.session_state.get("dual_cmp_llm"):
    with st.container():
        glass_anchor()
        st.markdown("### LLM comparison")
        st.markdown(st.session_state["dual_cmp_llm"])

if "dual_cmp" in st.session_state:
    projectA = os.path.splitext(zip_a.name)[0]
    projectB = os.path.splitext(zip_b.name)[0]

    res_a = st.session_state["dual_A"]
    res_b = st.session_state["dual_B"]
    cmp = st.session_state["dual_cmp"]

    with st.container():
        glass_anchor()
        st.subheader(f"Summary ({projectA} vs {projectB})")

        # quick top-line metrics
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Quality score of {projectA}", round(float(res_a.get("quality_score", 0)), 1))
        c2.metric(f"Quality score of {projectB}", round(float(res_b.get("quality_score", 0)), 1))
        c3.metric(f"Δ ({projectB} − {projectA})", round(float(res_b.get("quality_score", 0)) - float(res_a.get("quality_score", 0)), 2))

        # comparison table
        df_cmp = pd.DataFrame(cmp["metrics"])
        st.dataframe(df_cmp, use_container_width=True, hide_index=True)

        # grouped bars
        df_long = df_cmp.melt(id_vars=["metric"], value_vars=["A", "B"],
                          var_name="project", value_name="value")
        ch = (
            alt.Chart(df_long, title="Project comparison")
            .mark_bar()
            .encode(
                x=alt.X("metric:N", sort=None, axis=alt.Axis(labelAngle=-25, title=None)),
                y=alt.Y("value:Q", title=None),
                color=alt.Color("project:N", scale=alt.Scale(range=["#8287ba", "#b195c2"])),
                tooltip=["metric:N", "project:N", "value:Q"]
            )
        )
        st.altair_chart(ch, use_container_width=True)

        # hotspots side-by-side
        h1, h2 = st.columns(2)
        h1.subheader(f"Top hotspots — Project {projectA}")
        h1.dataframe(pd.DataFrame(cmp["top_hotspots"]["A"]), use_container_width=True, hide_index=True)
        h2.subheader(f"Top hotspots — Project {projectB}")
        h2.dataframe(pd.DataFrame(cmp["top_hotspots"]["B"]), use_container_width=True, hide_index=True)

    r1, r2 = st.columns(2, gap="large")

    with st.container():
        glass_anchor()
        st.header(f"Refactor ideas — {projectA}")
        ideas_a = (res_a or {}).get("refactor_ideas") or {}
        if ideas_a:
            for path, bullets in ideas_a.items():
                st.markdown(f"**{Path(path).name}**")
                for b in (bullets or [])[:8]:
                    st.write(f"- {b}")
                st.write("")
        else:
            st.caption("No LLM ideas produced for Project A.")

    with st.container():
        glass_anchor()
        st.subheader(f"Refactor ideas — {projectB}")
        ideas_b = (res_b or {}).get("refactor_ideas") or {}
        if ideas_b:
            for path, bullets in ideas_b.items():
                st.markdown(f"**{Path(path).name}**")
                for b in (bullets or [])[:8]:
                    st.write(f"- {b}")
                st.write("")
        else:
            st.caption("No LLM ideas produced for Project B.")



    # reports
    st.divider()
    st.subheader("Reports")


    fmt = st.radio("Choose report format:", ["JSON", "Markdown", "PDF"],
                   horizontal=True, key="report_format")

    rA1, rB2 = st.columns(2)
    with rA1:
        f"""Reports of the project {projectA}"""
        paths = res_a.get("report_paths", {})
        if fmt == "JSON" and "json" in paths:
            try:
                with open(paths["json"], "r", encoding="utf-8") as f:
                    st.download_button(
                        " Download JSON report",
                        data=f.read(),
                        file_name=Path(paths["json"]).name,
                        mime="application/json",
                        key="dl_json1",
                    )
            except Exception as e:
                st.error(f"Could not read JSON report: {e}")

        elif fmt == "Markdown" and "markdown" in paths:
            try:
                with open(paths["markdown"], "r", encoding="utf-8") as f:
                    content = f.read()
                    st.download_button(
                        " Download Markdown report",
                        data=content,
                        file_name=Path(paths["markdown"]).name,
                        mime="text/markdown",
                        key="dl_md1",
                    )
                    with st.expander("Preview (Markdown)"):
                        st.markdown(content)
            except Exception as e:
                st.error(f"Could not read Markdown report: {e}")

        elif fmt == "PDF" and "pdf" in paths:
            try:
                with open(paths["pdf"], "rb") as f:
                    st.download_button(
                        " Download PDF report",
                        data=f.read(),
                        file_name=Path(paths["pdf"]).name,
                        mime="application/pdf",
                        key="dl_pdf1",
                    )
            except Exception as e:
                st.error(f"Could not read PDF report: {e}")

        # debug
        with st.expander("Raw result (debug)", expanded=False):
            st.json(res_a)

    with rB2:
        f"""Reports of the project {projectB}"""
        paths = res_b.get("report_paths", {})
        if fmt == "JSON" and "json" in paths:
            try:
                with open(paths["json"], "r", encoding="utf-8") as f:
                    st.download_button(
                        " Download JSON report",
                        data=f.read(),
                        file_name=Path(paths["json"]).name,
                        mime="application/json",
                        key="dl_json2",
                    )
            except Exception as e:
                st.error(f"Could not read JSON report: {e}")

        elif fmt == "Markdown" and "markdown" in paths:
            try:
                with open(paths["markdown"], "r", encoding="utf-8") as f:
                    content = f.read()
                    st.download_button(
                        " Download Markdown report",
                        data=content,
                        file_name=Path(paths["markdown"]).name,
                        mime="text/markdown",
                        key="dl_md2",
                    )
                    with st.expander("Preview (Markdown)"):
                        st.markdown(content)
            except Exception as e:
                st.error(f"Could not read Markdown report: {e}")

        elif fmt == "PDF" and "pdf" in paths:
            try:
                with open(paths["pdf"], "rb") as f:
                    st.download_button(
                        " Download PDF report",
                        data=f.read(),
                        file_name=Path(paths["pdf"]).name,
                        mime="application/pdf",
                        key="dl_pdf2",
                    )
            except Exception as e:
                st.error(f"Could not read PDF report: {e}")

        # debug
        with st.expander("Raw result (debug)", expanded=False):
            st.json(res_b)

primary = st.get_option("theme.primaryColor") or "#F97316"  # istersen tema rengi
st.markdown(f"""
<style>
html {{ scroll-behavior: smooth; }}

.scroll-fab {{ position: fixed; right: 24px; z-index: 9999; }}
.scroll-fab a {{
  display:flex; align-items:center; justify-content:center;
  width:46px; height:46px; border-radius:999px;
  background: {primary}; color:#fff; text-decoration:none;
  opacity:.35;
  border:1px solid rgba(0,0,0,.08);
  box-shadow: 0 10px 25px rgba(0,0,0,.20);
  font-size:22px; line-height:1;
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}}
.scroll-fab a:hover, .scroll-fab a:focus {{ 
  opacity:1; 
  transform: translateY(-1px);
}}
.scroll-fab a:focus {{ outline: none; }}
.scroll-fab.top {{ bottom: 84px; }}   /* alttaki butonun üstüne gelsin */
.scroll-fab.bottom {{ bottom: 24px; }}
</style>

<div class="scroll-fab top"><a href="#page-top" aria-label="Yukarı git">↑</a></div>
<div class="scroll-fab bottom"><a href="#page-bottom" aria-label="Aşağı git">↓</a></div>
""", unsafe_allow_html=True)

st.markdown('<a id="page-bottom"></a>', unsafe_allow_html=True)