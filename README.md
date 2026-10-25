# MeClaw

## Overview
MeClaw is a local assistant that runs as a small web app. You chat with it in your browser, and it can manage files and folders in a sandboxed workspace through natural language. Replies come from either a local Ollama model or OpenAI, and the implementation stays modular and extensible.

<img width="1080" height="852" alt="image" src="https://github.com/user-attachments/assets/3dc5ceac-dc2d-4745-a92f-cbf835cc72b9" />


## Features
- Local web interface in a ChatGPT-like layout (FastAPI backend, static HTML/JS/CSS frontend, Turkish UI)
- Provider choice (Ollama or OpenAI) and model selection from the UI
- Settings dialog that edits .env and applies changes without a restart: Ollama address, OpenAI API key (never shown back), default provider/model, system prompt, and light/dark/system theme
- Streaming replies
- Chat history stored in SQLite (data/meclaw.db)
- Files panel (📁 in the top bar): browse the workspace, preview text, Word and image files, download, upload by drag and drop, and open the folder in the file manager; it refreshes when the assistant changes files
- 16 file and folder tools, restricted to the workspace folder (default: workspace/ in the project, changeable in Settings):
  - create, read, write, copy, rename, and delete files
  - create, list, move, rename, copy, zip, and extract folders and archives
  - DOCX read/write via python-docx
- Tool schemas stored externally in tools/finder/tool_definitions.json

## Project Structure
- server.py: FastAPI server (chat API and static file hosting)
- meclaw/: application package
  - config.py: settings loaded from .env
  - settings_store.py: writes settings changes back to .env
  - files.py: workspace listing, previews and uploads for the Files panel
  - agent.py: chat loop with tool calling
  - storage.py: SQLite conversation storage
  - llm/: provider layer (base.py, ollama.py, openai.py)
  - tools/registry.py: tool registry
- static/: web frontend (index.html, app.js, style.css)
- tools/finder/explorer_class.py: file and folder explorer implementation
- tools/finder/tool_definitions.json: tool schema definitions
- workspace/: default folder the tools operate in (git-ignored, created on first run)
- tests/: automated tests
- start.bat: Windows startup script

## Installation
1. Clone or download the repository.
2. Create and activate a Python environment if desired.
3. Install dependencies:
   pip install -r requirements.txt
4. Configure the app either from the Settings dialog (⚙ Ayarlar in the sidebar) or by copying .env.example to .env and editing it:
   - OLLAMA_HOST: Ollama address (default http://localhost:11434). Install and run Ollama to use local models.
   - OPENAI_API_KEY: required only to use the OpenAI provider.
   - MECLAW_DEFAULT_PROVIDER / MECLAW_DEFAULT_MODEL (optional): provider and model new chats start with.
   - MECLAW_SYSTEM_PROMPT (optional): custom system prompt; the built-in prompt is used when empty.
   - MECLAW_WORKSPACE (optional): absolute path of the folder the assistant works in; defaults to workspace/ in the project.
   - MECLAW_DB_PATH (optional): custom path for the SQLite database (restart required).

## Running the Project
- Windows: run start.bat (installs dependencies, starts Ollama if available, starts the server, and opens the browser).
- Any platform: python server.py

Then open http://127.0.0.1:8000.

## Testing
python -m pytest

## Development Notes
The project is in active development. Tool definitions are loaded from JSON, providers are pluggable through meclaw/llm, and conversations are persisted locally.
