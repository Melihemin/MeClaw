import logging
import os
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from ollama import AsyncClient 
from docx import Document
from docx.shared import Pt

path = os.path.dirname(os.path.abspath(__file__)) + "\\testdir"

# FILE MANIPULATION

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

def rename_file_tool(old_filename: str, new_filename: str) -> str:
    """Rename a file inside the tools directory.

    Args:
        old_filename: Current name of the file.
        new_filename: New name for the file.

    Returns:
        A status message describing the result.
    """
    if not old_filename or not new_filename:
        return "Old or new filename not provided."

    try:
        os.rename(os.path.join(path, old_filename), os.path.join(path, new_filename))
        return f"File '{old_filename}' renamed to '{new_filename}' successfully."
    except FileNotFoundError:
        return f"File '{old_filename}' not found."
    except Exception as e:
        logging.error(f"File Rename Error: {e}")
        return "Failed to rename the file."



# WORD file support

def read_word_file_tool(filename: str) -> str:
    """Read a Word (.docx) file inside the tools directory.

    Args:
        filename: Name of the Word file to read.

    Returns:
        The content of the Word file or an error message.
    """
    if not filename:
        return "No filename provided."

    try:
        doc = Document(os.path.join(path, filename))
        content = "\n".join([para.text for para in doc.paragraphs])
        return content

    except FileNotFoundError:
        return f"File '{filename}' not found."

    except Exception as e:
        logging.error(f"Word File Read Error: {e}")
        return "Failed to read the Word file."


def write_word_file_tool(filename: str, content: str, font_name: str = None, font_size: int = None) -> str:
    """Write content to a Word (.docx) file inside the tools directory.

    Args:
        filename: Name of the Word file to write to.
        content: Content to write into the Word file.
        font_name: (Optional) The name of the font to use (e.g., 'Arial', 'Times New Roman').
        font_size: (Optional) The size of the font in points (e.g., 12, 14).

    Returns:
        A status message describing the result.
    """
    if not filename:
        return "No filename provided."

    try:
        doc = Document()
        for line in content.splitlines():
            # Doğrudan paragrafa metin eklemek yerine, önce boş bir paragraf oluşturuyoruz
            paragraph = doc.add_paragraph()
            # Metni 'run' (metin bloğu) olarak ekliyoruz ki özelliklerini değiştirebilelim
            run = paragraph.add_run(line)
            
            # Eğer kullanıcı (veya LLM) font adı belirtmişse uygula
            if font_name:
                run.font.name = font_name
                
            # Eğer kullanıcı (veya LLM) font boyutu belirtmişse uygula (Pt formatında olmalı)
            if font_size:
                run.font.size = Pt(font_size)
                
        doc.save(os.path.join(path, filename))
        return f"Content written to '{filename}' successfully."

    except Exception as e:
        logging.error(f"Word File Write Error: {e}")
        return "Failed to write to the Word file."


# Folder and Path MANIPULATION

def create_folder_tool(folder_name: str) -> str:
    """Create a folder inside the tools directory.

    Args:
        folder_name: Name of the folder to create.

    Returns:
        A status message describing the result.
    """
    if not folder_name:
        return "No folder name provided."

    try:
        os.makedirs(os.path.join(path, folder_name), exist_ok=True)
        return f"Folder '{folder_name}' created successfully."
    except Exception as e:
        logging.error(f"Folder Creation Error: {e}")
        return "Failed to create the folder."


def remove_folder_tool(folder_name: str) -> str:
    """Remove a folder inside the tools directory.

    Args:
        folder_name: Name of the folder to remove.

    Returns:
        A status message describing the result.
    """
    if not folder_name:
        return "No folder name provided."

    try:
        os.rmdir(os.path.join(path, folder_name))
        return f"Folder '{folder_name}' removed successfully."
    except FileNotFoundError:
        return f"Folder '{folder_name}' not found."
    except OSError as e:
        logging.error(f"Folder Removal Error: {e}")
        return "Failed to remove the folder. Ensure it's empty before deletion."

# FILE COMMANDS

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


# FOLDER COMMANDS

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