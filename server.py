import json
import logging
import os
from pathlib import Path

import dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from ollama import AsyncClient 
from tools.finder.explorer_class import Explorer

explorer = Explorer()


def create_file_tool(filename: str) -> str:
    """Create a new file in the workspace."""
    return explorer.create_file(filename)


def delete_file_tool(filename: str) -> str:
    """Delete a file from the workspace."""
    return explorer.delete_file(filename)


def copy_file_tool(source_filename: str, destination_filename: str) -> str:
    """Copy one file to another location."""
    return explorer.copy_file(source_filename, destination_filename)


def read_file_tool(filename: str) -> str:
    """Read and return the contents of a text file."""
    return explorer.read_file(filename)


def write_file_tool(filename: str, content: str) -> str:
    """Write text content to a file."""
    return explorer.write_file(filename, content)


def rename_file_tool(old_filename: str, new_filename: str) -> str:
    """Rename an existing file."""
    return explorer.rename_file(old_filename, new_filename)


def write_word_file_tool(filename: str, content: str, font_name: str | None = None, font_size: int | None = None) -> str:
    """Create or overwrite a .docx file with the given content."""
    return explorer.write_word_file(filename, content, font_name, font_size)


def read_word_file_tool(filename: str) -> str:
    """Read the text content from a .docx file."""
    return explorer.read_word_file(filename)


def create_folder_tool(folder_name: str) -> str:
    """Create a new folder in the workspace."""
    return explorer.create_folder(folder_name)


def remove_folder_tool(folder_name: str) -> str:
    """Remove an empty folder from the workspace."""
    return explorer.remove_folder(folder_name)


def list_items_tool() -> str:
    """List files and folders available in the workspace root."""
    items = explorer.list_items()
    if not items:
        return "No items found."
    return "\n".join(f"{item['type']}: {item['name']}" for item in items)


def move_item_tool(source_path: str, destination_path: str) -> str:
    """Move a file or folder to a new path."""
    return explorer.move_item(source_path, destination_path)


def rename_folder_tool(old_folder_name: str, new_folder_name: str) -> str:
    """Rename a folder in the workspace."""
    return explorer.rename_folder(old_folder_name, new_folder_name)


def copy_folder_tool(source_folder_name: str, destination_folder_name: str) -> str:
    """Copy a folder to a new location."""
    return explorer.copy_folder(source_folder_name, destination_folder_name)


def zip_folder_tool(folder_name: str) -> str:
    """Create a .zip archive from a folder."""
    return explorer.zip_folder(folder_name)


def build_tool_definitions() -> list[dict]:
    definition_path = Path(__file__).resolve().parent / "tools" / "finder" / "tool_definitions.json"
    with definition_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


async def create_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_file(update, context)


async def delete_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_file(update, context)


async def copy_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await copy_file(update, context)


async def read_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await read_file(update, context)


async def write_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await write_file(update, context)


async def rename_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rename_file(update, context)


async def write_word_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await write_word_file(update, context)


async def read_word_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await read_word_file(update, context)


async def create_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_folder(update, context)


async def remove_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_folder(update, context)


async def list_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_items(update, context)


async def move_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await move_item(update, context)


async def rename_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rename_folder(update, context)


async def copy_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await copy_folder(update, context)


async def zip_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await zip_folder(update, context)

dotenv.load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! You can message me directly, no need to use /chat.")


async def tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available tools: /start, /tools, /create_file, /delete_file, /read_file, /write_file, /copy_file, /rename_file, /write_word_file, /read_word_file, /create_folder, /remove_folder, /list_items, /move_item, /rename_folder, /copy_folder, /zip_folder")


async def create_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a filename: /create_file example.txt")
        return

    filename = parts[1].strip()
    result = create_file_tool(filename)
    await update.message.reply_text(result)


async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a filename: /delete_file example.txt")
        return

    filename = parts[1].strip()
    result = delete_file_tool(filename)
    await update.message.reply_text(result)


async def copy_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide source and destination filenames: /copy_file source.txt destination.txt")
        return

    source_filename = parts[1].strip()
    destination_filename = parts[2].strip()
    result = copy_file_tool(source_filename, destination_filename)
    await update.message.reply_text(result)


async def read_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a filename: /read_file example.txt")
        return

    filename = parts[1].strip()
    result = read_file_tool(filename)
    await update.message.reply_text(result)


async def write_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide a filename and content: /write_file example.txt 'Your content here'")
        return

    filename = parts[1].strip()
    content = parts[2].strip()
    result = write_file_tool(filename, content)
    await update.message.reply_text(result)


async def rename_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide old and new filenames: /rename_file old.txt new.txt")
        return

    old_filename = parts[1].strip()
    new_filename = parts[2].strip()
    result = rename_file_tool(old_filename, new_filename)
    await update.message.reply_text(result)


async def write_word_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 3)
    if len(parts) <= 3 or not parts[1].strip() or not parts[2].strip() or not parts[3].strip():
        await update.message.reply_text("Please provide a filename, content, and optionally font name and size: /write_word_file example.docx 'Your content here' 'Arial' 12")
        return

    filename = parts[1].strip()
    content = parts[2].strip()
    font_name = parts[3].strip() if len(parts) > 3 else None
    font_size = int(parts[4].strip()) if len(parts) > 4 else None
    result = write_word_file_tool(filename, content, font_name, font_size)
    await update.message.reply_text(result)


async def read_word_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a filename: /read_word_file example.docx")
        return

    filename = parts[1].strip()
    result = read_word_file_tool(filename)
    await update.message.reply_text(result)


async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a folder name: /create_folder example_folder")
        return

    folder_name = parts[1].strip()
    result = create_folder_tool(folder_name)
    await update.message.reply_text(result)


async def remove_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a folder name: /remove_folder example_folder")
        return

    folder_name = parts[1].strip()
    result = remove_folder_tool(folder_name)
    await update.message.reply_text(result)


async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = list_items_tool()
    # Edit result for better readability beautify the output
    await update.message.reply_text(result)


async def move_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide source and destination paths: /move_item source.txt destination.txt")
        return

    source_path = parts[1].strip()
    destination_path = parts[2].strip()
    result = move_item_tool(source_path, destination_path)
    await update.message.reply_text(result)


async def rename_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide old and new folder names: /rename_folder old_name new_name")
        return

    old_folder_name = parts[1].strip()
    new_folder_name = parts[2].strip()
    result = rename_folder_tool(old_folder_name, new_folder_name)
    await update.message.reply_text(result)


async def copy_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide source and destination folder names: /copy_folder source_folder destination_folder")
        return

    source_folder_name = parts[1].strip()
    destination_folder_name = parts[2].strip()
    result = copy_folder_tool(source_folder_name, destination_folder_name)
    await update.message.reply_text(result)


async def zip_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a folder name: /zip_folder example_folder")
        return

    folder_name = parts[1].strip()
    result = zip_folder_tool(folder_name)
    await update.message.reply_text(result)


async def run_llm_with_tools(user_text: str) -> str:
    client = AsyncClient()
    messages = [
        {
            'role': 'system',
            'content': (
                'You are a friendly and conversational AI assistant for Melih Emin KILICOGLU. '
                'You can chat naturally, answer questions, and assist with general tasks. '
                'When the user\'s request involves managing files and folders (such as creating, reading, deleting, or renaming), '
                'proactively use the appropriate tools to fulfill the request. '
                'Always explain the results of your actions clearly and kindly after using a tool. '
                '\n\nSTRICT RULES FOR CONVERSATION: '
                '1. If the user is just chatting normally (e.g., "how are you", "hello"), respond directly and naturally like a human. '
                '2. NEVER mention your internal tools, say things like "No tool call is needed", or explain your decision-making process. Just give the final answer.'
            )
        },
        {
            'role': 'user',
            'content': user_text,
        },
    ]

    tools = build_tool_definitions()

    for _ in range(5):
        response = await client.chat(
            model='Qwen3:8b',
            messages=messages,
            tools=tools,
        )
        message = response['message']
        message_dict = message.model_dump(exclude_none=True) if hasattr(message, 'model_dump') else message
        messages.append(message_dict)

        tool_calls = message_dict.get('tool_calls') or []
        if not tool_calls:
            return message_dict.get('content', '') or 'No response returned.'

        for tool_call in tool_calls:
            function = tool_call['function']
            tool_name = function['name']
            arguments = function.get('arguments', {}) or {}

            if tool_name == 'create_file_tool':
                tool_result = create_file_tool(arguments.get('filename', ''))
                if tool_result == 'No filename provided.':
                    return 'Please provide a filename, for example: /create_file example.txt'
                return tool_result
            elif tool_name == 'delete_file_tool':
                tool_result = delete_file_tool(arguments.get('filename', ''))
                if tool_result == 'No filename provided.':
                    return 'Please provide a filename, for example: /delete_file example.txt'
                return tool_result
            elif tool_name == 'copy_file_tool':
                tool_result = copy_file_tool(arguments.get('source_filename', ''), arguments.get('destination_filename', ''))
                if tool_result == 'Source or destination filename not provided.':
                    return 'Please provide source and destination filenames, for example: /copy_file source.txt destination.txt'
                return tool_result
            elif tool_name == 'read_file_tool':
                tool_result = read_file_tool(arguments.get('filename', ''))

                if tool_result == 'No filename provided.':
                    return 'Please provide a filename, for example: /read_file example.txt'

                return tool_result

            elif tool_name == 'write_file_tool':
                tool_result = write_file_tool(arguments.get('filename', ''), arguments.get('content', ''))
                if tool_result == 'No filename provided.':
                    return 'Please provide a filename and content, for example: /write_file example.txt "Your content here"'
                return tool_result
            elif tool_name == 'rename_file_tool':
                tool_result = rename_file_tool(arguments.get('old_filename', ''), arguments.get('new_filename', ''))
                if tool_result == 'Old or new filename not provided.':
                    return 'Please provide old and new filenames, for example: /rename_file old.txt new.txt'
                return tool_result
            elif tool_name == 'write_word_file_tool':
                tool_result = write_word_file_tool(arguments.get('filename', ''), arguments.get('content', ''), arguments.get('font_name', None), arguments.get('font_size', None))
                if tool_result == 'No filename provided.':
                    return 'Please provide a filename and content, for example: /write_word_file example.docx "Your content here" "Arial" 12'
                return tool_result
            elif tool_name == 'read_word_file_tool':
                tool_result = read_word_file_tool(arguments.get('filename', ''))
                if tool_result == 'No filename provided.':
                    return 'Please provide a filename, for example: /read_word_file example.docx'
                return tool_result
            elif tool_name == 'create_folder_tool':
                tool_result = create_folder_tool(arguments.get('folder_name', ''))
                if tool_result == 'No folder name provided.':
                    return 'Please provide a folder name, for example: /create_folder example_folder'
                return tool_result
            elif tool_name == 'remove_folder_tool':
                tool_result = remove_folder_tool(arguments.get('folder_name', ''))
                if tool_result == 'No folder name provided.':
                    return 'Please provide a folder name, for example: /remove_folder example_folder'
                return tool_result
            elif tool_name == 'list_items_tool':
                return list_items_tool()
            elif tool_name == 'move_item_tool':
                return move_item_tool(arguments.get('source_path', ''), arguments.get('destination_path', ''))
            elif tool_name == 'rename_folder_tool':
                return rename_folder_tool(arguments.get('old_folder_name', ''), arguments.get('new_folder_name', ''))
            elif tool_name == 'copy_folder_tool':
                return copy_folder_tool(arguments.get('source_folder_name', ''), arguments.get('destination_folder_name', ''))
            elif tool_name == 'zip_folder_tool':
                return zip_folder_tool(arguments.get('folder_name', ''))
            else:
                tool_result = f'Unknown tool: {tool_name}'

            messages.append({
                'role': 'tool',
                'tool_name': tool_name,
                'content': tool_result,
            })

    return 'Tool handling limit reached before the model produced a final answer.'


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Capture all normal text messages (excluding commands)
    user_text = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action=constants.ChatAction.TYPING
    )

    try:
        response_text = await run_llm_with_tools(user_text)
        await update.message.reply_text(response_text)

    except Exception as e:
        # Log the error in the console and notify the user
        logging.error(f"Ollama Error: {e}")
        await update.message.reply_text("Sorry, I cannot respond right now. Please make sure Ollama is running in the background.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(os.getenv('TELEGRAM_API')).build()
    
    # Handler for the /start command
    application.add_handler(CommandHandler('start', start))
    
    # Handler for the /tools command
    application.add_handler(CommandHandler('tools', tools))

    # Handler for the /create_file command
    application.add_handler(CommandHandler('create_file', create_file_command))

    # Handler for the /delete_file command
    application.add_handler(CommandHandler('delete_file', delete_file_command))

    # Handler for the /copy_file command
    application.add_handler(CommandHandler('copy_file', copy_file_command))

    # Handler for the /read_file command
    application.add_handler(CommandHandler('read_file', read_file_command))

    # Handler for the /write_file command
    application.add_handler(CommandHandler('write_file', write_file_command))

    # Handler for the /rename_file command
    application.add_handler(CommandHandler('rename_file', rename_file_command))

    # Handler for the /write_word_file command
    application.add_handler(CommandHandler('write_word_file', write_word_file_command))

    # Handler for the /read_word_file command
    application.add_handler(CommandHandler('read_word_file', read_word_file_command))

    # Handler for the /create_folder command
    application.add_handler(CommandHandler('create_folder', create_folder_command))

    # Handler for the /remove_folder command
    application.add_handler(CommandHandler('remove_folder', remove_folder_command))

    application.add_handler(CommandHandler('list_items', list_items_command))
    application.add_handler(CommandHandler('move_item', move_item_command))
    application.add_handler(CommandHandler('rename_folder', rename_folder_command))
    application.add_handler(CommandHandler('copy_folder', copy_folder_command))
    application.add_handler(CommandHandler('zip_folder', zip_folder_command))

    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    application.run_polling()