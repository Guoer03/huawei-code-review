"""Keep Python locations while excluding comments and string literals."""
from __future__ import annotations

import io
import tokenize


def code_only(text: str) -> str:
    lines = text.splitlines(keepends=True)
    masked = [list(line) for line in lines]
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        for row in range(token.start[0], token.end[0] + 1):
            start = token.start[1] if row == token.start[0] else 0
            end = token.end[1] if row == token.end[0] else len(masked[row - 1])
            for column in range(start, end):
                if masked[row - 1][column] not in '\r\n':
                    masked[row - 1][column] = ' '
    return ''.join(''.join(line) for line in masked)
