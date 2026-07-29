from __future__ import annotations

import re


def md_to_html(text: str) -> str:
    text = re.sub(r'```(\w*)\n(.*?)```', r'<pre>\2</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    text = re.sub(r'(?m)^###\s+(.+)$', r'<b>\1</b>', text)
    text = re.sub(r'(?m)^##\s+(.+)$', r'<b>\1</b>', text)
    text = re.sub(r'(?m)^#\s+(.+)$', r'<b>\1</b>', text)

    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    text = re.sub(r'&', '&amp;', text)
    text = re.sub(r'<', '&lt;', text)
    text = re.sub(r'>', '&gt;', text)
    text = re.sub(r'&lt;pre&gt;(.*?)&lt;/pre&gt;', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'&lt;code&gt;(.*?)&lt;/code&gt;', r'<code>\1</code>', text)

    return text.strip()


def md_to_text(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?m)^###\s*', '', text)
    text = re.sub(r'(?m)^##\s*', '', text)
    text = re.sub(r'(?m)^#\s*', '', text)
    text = re.sub(r'(?m)^\*\s+', '- ', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'```(\w*)\n(.*?)```', r'\2', text, flags=re.DOTALL)
    return text.strip()
