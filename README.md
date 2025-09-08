# CodeInsight Mini

A small Streamlit app that analyzes Python projects with **Radon** (MI/CC), **Pylint**, and optional LLM suggestions (Ollama/OpenAI). Exports **JSON / Markdown / PDF** reports.

## Features
- Upload a `.zip` of your code
- Radon (Maintainability Index & Cyclomatic Complexity)
- Pylint (linting summary + raw messages)
- Recommendations + optional LLM refactor ideas
- Report export: JSON / Markdown / PDF (with charts)

## Quickstart
```bash
# 1) create & activate venv
python -m venv venv
# Windows:
venv\Scripts\activate

# 2) install deps
pip install -r requirements.txt

# 3) run UI
streamlit run codeinsight/ui/app.py
