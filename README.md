# MeClaw

## Overview
MeClaw is a local assistant project that combines a Telegram bot with file-management capabilities and an Ollama-powered conversational layer. The project is designed to let users interact with files and folders through natural language while keeping the implementation modular and extensible.

<img width="1080" height="852" alt="image" src="https://github.com/user-attachments/assets/3dc5ceac-dc2d-4745-a92f-cbf835cc72b9" />


## Current Features
- Telegram bot entry point in server.py
- Class-based file and folder explorer in tools/finder/explorer_class.py
- Tool schemas stored externally in tools/finder/tool_definitions.json
- Support for creating, reading, writing, copying, renaming, and deleting files
- Support for creating, listing, moving, renaming, copying, zipping, and extracting folders and archives
- DOCX read/write support via python-docx
- Desktop helper app in desktop_app.py for editing environment settings and launching the bot
- Windows startup script in start.bat and shell script in start.sh
- Regression tests under tests/test_explorer_class.py and tests/test_desktop_env.py

## Project Structure
- server.py: Telegram bot logic and tool wrapper functions
- desktop_app.py: simple desktop UI for editing .env values and launching the app
- tools/finder/explorer_class.py: main explorer implementation
- tools/finder/tool_definitions.json: Ollama tool schema definitions
- tools/finder/testdir/: sample workspace used by the explorer
- tests/test_explorer_class.py: functional tests for core explorer behavior
- tests/test_desktop_env.py: tests for environment and desktop helper logic

## Installation
1. Clone or download the repository.
2. Create and activate a Python environment if desired.
3. Install dependencies:
   pip install -r requirements.txt
4. Make sure Ollama is installed and running locally.
5. Set the Telegram bot token in the environment as TELEGRAM_API.
6. Optionally configure OLLAMA_HOST in the .env file.

## Running the Project
### Option 1: Start the server directly
- Python:
  python server.py

### Option 2: Use the startup scripts
- Windows:
  start.bat

## Usage
Once the bot is running, you can interact with it through Telegram.

Available commands include:
- /start
- /tools
- /create_file
- /delete_file
- /copy_file
- /read_file
- /write_file
- /rename_file
- /write_word_file
- /read_word_file
- /create_folder
- /remove_folder
- /list_items
- /move_item
- /rename_folder
- /copy_folder
- /zip_folder
- /extract_archive

Example:
- Create a file: /create_file notes.txt
- Read a file: /read_file notes.txt

## Development Notes
The project is currently in active development and is being refactored toward a more maintainable architecture. The explorer logic is now class-based, tool definitions are loaded from JSON, and a small desktop helper is included for easier setup and launching.
