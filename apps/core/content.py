import re
from html import escape

from django.utils.safestring import mark_safe


def render_content(value):
    """Small, escaped text format: paragraphs, explicit lists and subheadings."""
    blocks, paragraph, items = [], [], []
    list_tag = None

    def flush_paragraph():
        if paragraph:
            blocks.append('<p>' + '<br>'.join(paragraph) + '</p>')
            paragraph.clear()

    def flush_list():
        nonlocal list_tag
        if items:
            blocks.append(f'<{list_tag}>' + ''.join(f'<li>{item}</li>' for item in items) + f'</{list_tag}>')
            items.clear()
        list_tag = None

    for raw_line in str(value or '').replace('\r\n', '\n').split('\n'):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r'^(#{2,3})\s+(.+)$', line)
        bullet = re.match(r'^[-*•]\s+(.+)$', line)
        numbered = re.match(r'^\d+[.)]\s+(.+)$', line)
        if heading:
            flush_paragraph()
            flush_list()
            tag = 'h3' if len(heading[1]) == 2 else 'h4'
            blocks.append(f'<{tag}>{escape(heading[2])}</{tag}>')
        elif bullet or numbered:
            flush_paragraph()
            tag = 'ul' if bullet else 'ol'
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            items.append(escape((bullet or numbered)[1]))
        else:
            flush_list()
            paragraph.append(escape(line))
    flush_paragraph()
    flush_list()
    return mark_safe('\n'.join(blocks))
