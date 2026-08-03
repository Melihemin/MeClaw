import logging
import os
import dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from ollama import AsyncClient 
from tools.finder.explorer import (
    create_file as create_file_command,
    create_file_tool,
    delete_file as delete_file_command,
    delete_file_tool,
    copy_file as copy_file_command,
    copy_file_tool,
    read_file as read_file_command,
    read_file_tool,
    write_file as write_file_command,
    write_file_tool,
    rename_file as rename_file_command,
    rename_file_tool,
    write_word_file as write_word_file_command,
    write_word_file_tool,
    read_word_file as read_word_file_command,
    read_word_file_tool
)

dotenv.load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! You can message me directly, no need to use /chat.")


async def tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Available tools: /start, /tools, /create_file, /delete_file. Natural language messages can also trigger file tools when the model decides.")

async def run_llm_with_tools(user_text: str) -> str:
    client = AsyncClient()
    messages = [
        {
            'role': 'system',
            'content': (
                'You are a friendly and conversational AI assistant for Melih Emin KILICOGLU. '
                'You can chat naturally, answer questions, and assist with general tasks. '
                'When the user\'s request involves managing files (such as creating, reading, deleting, or renaming), '
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

    tools = [create_file_tool, delete_file_tool, copy_file_tool, read_file_tool, write_file_tool, rename_file_tool, write_word_file_tool, read_word_file_tool]

    for _ in range(5):
        response = await client.chat(
            model='llama3.1:8b',
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

    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    application.run_polling()