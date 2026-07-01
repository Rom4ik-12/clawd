import re
import html

def escape_html(text: str) -> str:
    """Экранирует <, >, & для безопасной вставки в HTML, кроме разрешённых тегов (если они уже есть)."""
    return html.escape(text, quote=False)

def md_to_html(text: str) -> str:
    if not text:
        return text

    # Сначала экранируем весь текст, чтобы случайные < и > (не относящиеся к HTML) не ломали парсер Telethon
    # Но мы должны быть осторожны, так как мы сами будем вставлять < и > для форматирования.
    # Поэтому мы сначала экранируем:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Вспомогательный массив для сохранения блоков кода, чтобы внутри них не срабатывали регулярки для bold/italic и т.д.
    code_blocks = []
    
    def code_replacer(match):
        lang = match.group(1).strip() if match.group(1) else ""
        code = match.group(2)
        idx = len(code_blocks)
        if lang:
            code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
        else:
            code_blocks.append(f'<pre>{code}</pre>')
        return f"%%CODE_BLOCK_{idx}%%"

    # 1. Извлекаем многострочные блоки кода ```lang...```
    text = re.sub(r'```(\w+)?\n?(.*?)```', code_replacer, text, flags=re.DOTALL)

    def inline_code_replacer(match):
        code = match.group(1)
        idx = len(code_blocks)
        code_blocks.append(f'<code>{code}</code>')
        return f"%%CODE_BLOCK_{idx}%%"

    # 2. Извлекаем инлайн-код `code`
    text = re.sub(r'`([^`\n]+)`', inline_code_replacer, text)

    # 3. Blockquotes (сворачиваемые)
    # Ищем строки, начинающиеся с > (точнее &gt; из-за экранирования)
    # Собираем их вместе.
    def blockquote_replacer(match):
        content = match.group(1)
        # убираем > из начала каждой строки внутри
        content = re.sub(r'^&gt;\s?', '', content, flags=re.MULTILINE)
        return f'<blockquote expandable>{content}</blockquote>'
    
    text = re.sub(r'((?:^&gt;.*(?:\n|$))+)', blockquote_replacer, text, flags=re.MULTILINE)

    # 4. Bold **text**
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # 5. Underline __text__
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)

    # 6. Italic *text* или _text_
    # Игнорируем _ если он внутри слова
    text = re.sub(r'(?<![A-Za-z0-9])\*(.*?)\*(?![A-Za-z0-9])', r'<i>\1</i>', text)
    text = re.sub(r'(?<![A-Za-z0-9])_(.*?)_(?![A-Za-z0-9])', r'<i>\1</i>', text)

    # 7. Strikethrough ~~text~~
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)

    # 8. Spoiler ||text||
    text = re.sub(r'\|\|(.*?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', text)

    # 9. Links [text](url)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    # Возвращаем блоки кода обратно
    for i, block in enumerate(code_blocks):
        text = text.replace(f"%%CODE_BLOCK_{i}%%", block)

    return text
