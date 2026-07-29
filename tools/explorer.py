import logging
import os
import dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from ollama import AsyncClient 

path = os.path.dirname(os.path.abspath(__file__)) + "\\testdir"


def create_file_tool(filename: str) -> str:
    """Create an empty file inside the tools directory.

    Args:
        filename: Name of the file to create.

    Returns:
        A status message describing the result.
    """
    if not filename:
        return "No filename provided."

    try:
        with open(os.path.join(path, filename), 'w', encoding='utf-8') as file:
            file.write('')
        return f"File '{filename}' created successfully."
    except Exception as e:
        logging.error(f"File Creation Error: {e}")
        return "Failed to create the file."


def delete_file_tool(filename: str) -> str:
    """Delete a file inside the tools directory.

    Args:
        filename: Name of the file to delete.

    Returns:
        A status message describing the result.
    """
    if not filename:
        return "No filename provided."

    try:
        os.remove(os.path.join(path, filename))
        return f"File '{filename}' deleted successfully."
    except Exception as e:
        logging.error(f"File Deletion Error: {e}")
        return "Failed to delete the file."


def copy_file_tool(source_filename: str, destination_filename: str) -> str:
    """Copy a file inside the tools directory.

    Args:
        source_filename: Name of the source file to copy.
        destination_filename: Name of the destination file.

    Returns:
        A status message describing the result.
    """
    if not source_filename or not destination_filename:
        return "Source or destination filename not provided."

    try:
        with open(os.path.join(path, source_filename), 'r', encoding='utf-8') as src_file:
            content = src_file.read()
        with open(os.path.join(path, destination_filename), 'w', encoding='utf-8') as dest_file:
            dest_file.write(content)
        return f"File '{source_filename}' copied to '{destination_filename}' successfully."
    except Exception as e:
        logging.error(f"File Copy Error: {e}")
        return "Failed to copy the file."


def read_file_tool(filename: str) -> str:

    """Read a file inside the tools directory.

    Args:
        filename: Name of the file to Read.

    Returns:
        A status message describing the result.
    """

    if not filename:
        return "No filename provided."

    try:
        with open(os.path.join(path, filename), "r", encoding="utf-8") as file:
            content = file.read()

        return content

    except FileNotFoundError:
        return f"File '{filename}' not found."

    except Exception as e:
        logging.error(f"File Read Error: {e}")
        return "Failed to read the file"


def write_file_tool(filename: str, content: str) -> str:
    """Write content to a file inside the tools directory.

    Args:
        filename: Name of the file to write to.
        content: Content to write into the file.

    Returns:
        A status message describing the result.
    """
    if not filename:
        return "No filename provided."

    try:
        with open(os.path.join(path, filename), 'w', encoding='utf-8') as file:
            file.write(content)
        return f"Content written to '{filename}' successfully."

    except FileNotFoundError:
        return f"File '{filename}' not found."
    
    except Exception as e:
        logging.error(f"File Write Error: {e}")
        return "Failed to write to the file."

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


async def read_file(update: Update, contect: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide a filename: /read_file example.txt")
        return

    filename = parts[1].strip()
    result = read_file_tool(filename)
    await update.message.reply_text(result)

async def copy_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 1)
    if len(parts) <= 1 or not parts[1].strip():
        await update.message.reply_text("Please provide source and destination filenames: /copy_file source.txt destination.txt")
        return
    
async def write_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) <= 2 or not parts[1].strip() or not parts[2].strip():
        await update.message.reply_text("Please provide a filename and content: /write_file example.txt 'Your content here'")
        return

    filename = parts[1].strip()
    content = parts[2].strip()
    result = write_file_tool(filename, content)
    await update.message.reply_text(result)
    