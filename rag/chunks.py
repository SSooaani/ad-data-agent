"""Split Markdown at headings and paragraph/table-row boundaries, preserving code fences."""
import hashlib
import re

from .settings import DOCUMENTS, ROOT


def document_hashes():
    return {name: hashlib.sha256((ROOT / 'knowledge' / name).read_bytes()).hexdigest()
            for name in DOCUMENTS}


def load_chunks():
    chunks = []
    for filename, category in DOCUMENTS.items():
        lines = (ROOT / 'knowledge' / filename).read_text(encoding='utf-8').splitlines()
        title = lines[0].lstrip('# ').strip()
        starts = []
        in_code = False
        for i, line in enumerate(lines):
            if line.startswith('```'):
                in_code = not in_code
            if not in_code and line.startswith('## '):
                starts.append(i)
        # Include the preamble in its own section, and attach its context to other chunks.
        context_end = starts[0] if starts else len(lines)
        context = '\n'.join(lines[1:context_end]).strip()[:380]
        bounds = sorted(set([0, *starts, len(lines)]))
        for start, end in zip(bounds, bounds[1:]):
            heading = lines[start].lstrip('# ').strip()
            section = lines[start + 1:end]
            # An entire fenced SQL block is one unit; prose and table rows are units.
            units, buffer, code = [], [], False
            for i, line in enumerate(section, start + 1):
                if line.startswith('```'):
                    if not code and buffer:
                        units.append(buffer)
                        buffer = []
                    buffer.append((i, line))
                    code = not code
                    if not code:
                        units.append(buffer)
                        buffer = []
                elif code:
                    buffer.append((i, line))
                else:
                    if buffer:
                        units.append(buffer)
                        buffer = []
                    if line.strip():
                        units.append([(i, line)])
            if buffer:
                units.append(buffer)
            parts, current, size = [], [], 0
            for unit in units:
                length = sum(len(line) + 1 for _, line in unit)
                if current and size + length > 780:
                    parts.append(current)
                    current, size = [], 0
                current.extend(unit)
                size += length
            if current:
                parts.append(current)
            for part, content in enumerate(parts):
                body = '\n'.join(line for _, line in content)
                prefix = f'# {title}\n���{category}\n'
                if start and context:
                    prefix += context + '\n'
                text = prefix + f'## {heading}\n' + body
                identifier = hashlib.sha256(f'{filename}:{start}:{part}:{text}'.encode()).hexdigest()
                chunks.append({'id': identifier, 'text': text, 'metadata': {
                    'source': f'knowledge/{filename}', 'category': category,
                    'heading': heading, 'part': part + 1,
                    'line_start': content[0][0] + 1, 'line_end': content[-1][0] + 1,
                }})
    if not chunks:
        raise RuntimeError('The three knowledge documents produced no chunks.')
    return chunks
