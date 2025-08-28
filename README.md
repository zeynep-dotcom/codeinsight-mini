# CodeInsight Mini — Google-ADK Workflow Ready

Analyze Python projects with **Radon** (MI/CC), **Pylint**, and optional LLM suggestions, orchestrated by an **ADK-style workflow**. Export results as **JSON / Markdown / PDF** from a simple **Streamlit** UI.

> **Distinct feature:** Designed to run as a **Google ADK** workflow when ADK is available, and **fall back to a built-in flow** when it isn’t. Either way, you get the same results and UX.

---

## Highlights

- **ADK workflow design**
  - Steps: **Radon → Pylint → Recommendations → (optional) LLM Refactor Ideas → Merge/Report**
  - If **`google-adk`** is installed, the app is ready to run under an ADK workflow model.
  - If ADK isn’t present, a **manual runner** executes the exact same steps—no setup friction.
- **Pluggable AI agents**
  - Choose in the sidebar: **Ollama (local)**, **OpenAI**, or **No AI (raw results)**.
  - A tiny **agent factory** standardizes `.generate(prompt)` across providers.
- **Actionable metrics**
  - Radon: Maintainability Index & Cyclomatic Complexity
  - Pylint: message summary + raw messages
  - File-level scores + project-level recommendations
- **One-click reports**: **JSON**, **Markdown**, **PDF** (charts embedded)
- **Windows-friendly**: No native deps required for PDF (uses `fpdf2`)

---

## Quickstart

```bash
# 1) create & activate venv
python -m venv venv
# Windows:
venv\Scripts\activate

# 2) install dependencies
pip install -r requirements.txt

# 3) (optional) enable Google ADK
#   If you want to experiment with ADK, install it too:
# pip install google-adk

# 4) run the UI
streamlit run codeinsight/ui/app.py
