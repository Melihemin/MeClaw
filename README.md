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
- Tools the assistant can call during a chat (defined in meclaw/tools/):
  - 19 file and folder tools, restricted to the workspace folder (default: workspace/ in the project, changeable in Settings):
    - create, read (optionally a line range), write, edit (replace one unique snippet or append), copy, rename, move, and delete files
    - create, list (optionally recursive), rename, copy, move, and remove empty folders
    - zip and extract archives; search files by name or content; show file info
    - DOCX read/write via python-docx
  - Documents: read PDF text by page range (pypdf); read and write .xlsx and .csv spreadsheets (openpyxl)
  - Utilities: current date, time and weekday; a safe calculator for arithmetic expressions (no eval)
  - Web (on by default, toggle in Settings or MECLAW_INTERNET): fetch_url reads a public http/https page as text, and web_search runs a DuckDuckGo search. Local, private and LAN addresses are blocked.
  - Memory (on by default, toggle in Settings or MECLAW_MEMORY): remember and forget durable facts about you. Saved notes are stored in SQLite and the most recent ones are added to the system prompt.
- Destructive or overwriting actions ask for confirmation first: deleting files or folders, overwriting or moving over existing items, zipping over an existing archive, extracting into a non-empty folder, editing a file, and overwriting an existing spreadsheet. The chat shows a confirmation card with a preview, and the change runs only after you approve it.
- Tool results longer than 20,000 characters are truncated.

## Project Structure
- server.py: FastAPI server (chat API and static file hosting)
- meclaw/: application package
  - config.py: settings loaded from .env
  - settings_store.py: writes settings changes back to .env
  - files.py: workspace listing, previews and uploads for the Files panel
  - agent.py: chat loop with tool calling
  - memory.py: memory rules and the known-facts block added to the system prompt
  - storage.py: SQLite conversation and memory storage
  - llm/: provider layer (base.py, ollama.py, openai.py)
  - tools/: tools the assistant can call
    - __init__.py: build_registry, which picks the tool set from the settings
    - base.py: ToolSpec, ToolContext and ToolRegistry (runs tools, caps results, asks for confirmation)
    - files.py: file and folder tools built on the Explorer
    - documents.py: PDF and spreadsheet tools
    - web.py: fetch_url and web_search, with the private-address guard
    - utils.py: date/time and calculator tools
    - memory.py: remember and forget tools
- static/: web frontend (index.html, app.js, style.css)
- tools/finder/explorer_class.py: file and folder explorer implementation
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
   - MECLAW_INTERNET (optional): set to 0, false, off or no to disable the web tools (fetch_url, web_search). On by default.
   - MECLAW_MEMORY (optional): set to 0, false, off or no to disable the memory tools and stop adding saved notes to the prompt. On by default.

## Running the Project
- Windows: run start.bat (installs dependencies, starts Ollama if available, starts the server, and opens the browser).
- Any platform: python server.py

Then open http://127.0.0.1:8000.

## Testing
python -m pytest

## Development Notes
The project is in active development. Tools are declared as ToolSpec entries in meclaw/tools/, providers are pluggable through meclaw/llm, and conversations are persisted locally.
