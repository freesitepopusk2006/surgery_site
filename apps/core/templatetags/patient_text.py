from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


register = template.Library()


LIST_ITEM_MAX_LENGTH = 240


def _split_blocks(value):
    blocks = []
    current = []

    for raw_line in str(value or '').replace('\r\n', '\n').split('\n'):
        line = raw_line.strip()
        if line:
            current.append(line)
            continue

        if current:
            blocks.append('\n'.join(current))
            current = []

    if current:
        blocks.append('\n'.join(current))

    return blocks


def _is_list_item(block):
    if '\n' in block:
        return False
    if len(block) > LIST_ITEM_MAX_LENGTH:
        return False
    if block.endswith(':'):
        return False
    return True


def _render_paragraph(block):
    escaped = conditional_escape(block).replace('\n', '<br>')
    return f'<p>{escaped}</p>'


def _render_list(items):
    rendered_items = ''.join(f'<li>{conditional_escape(item)}</li>' for item in items)
    return f'<ul class="patient-bullet-list">{rendered_items}</ul>'


@register.filter
def patient_text(value):
    blocks = _split_blocks(value)
    rendered = []
    index = 0

    while index < len(blocks):
        block = blocks[index]
        previous = blocks[index - 1] if index else ''

        should_start_list = (
            _is_list_item(block)
            and (
                previous.endswith(':')
                or (
                    index + 1 < len(blocks)
                    and _is_list_item(blocks[index + 1])
                )
            )
        )

        if should_start_list:
            items = []
            while index < len(blocks) and _is_list_item(blocks[index]):
                items.append(blocks[index])
                index += 1
            rendered.append(_render_list(items))
            continue

        rendered.append(_render_paragraph(block))
        index += 1

    return mark_safe('\n'.join(rendered))
