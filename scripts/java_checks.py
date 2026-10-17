"""Bounded Java lexical checks; these are not a Java parser or a compiler.

Comments/literals are masked without changing offsets, then balanced token
delimiters locate control-flow bodies. Classic case labels are review candidates
only: their presence does not prove a missing break or illegal fall-through.
Unicode-escape preprocessing, type analysis and malformed-source diagnostics are
outside this helper's scope. It does not claim complete Java rule coverage.
Only braced do-while bodies are recognized when excluding the trailing while;
unbraced do bodies require fuller statement parsing and may be reported again.
"""
from __future__ import annotations

from bisect import bisect_right
import re


BRACES = "HUAWEI-JAVA-FORMAT-002"
SWITCH = "HUAWEI-JAVA-SWITCH-001"
_TOKEN = re.compile(r"[A-Za-z_$][\w$]*|->|::|[^\s]")


def _mask_noncode(text: str) -> str:
    masked = list(text)
    i = 0
    while i < len(text):
        start = i
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            i = len(text) if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
        elif text[i] in "\"'":
            delimiter = '"""' if text.startswith('"""', i) else text[i]
            i += len(delimiter)
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text.startswith(delimiter, i):
                    i += len(delimiter)
                    break
                else:
                    i += 1
            i = min(i, len(text))
        else:
            i += 1
            continue
        for position in range(start, i):
            if text[position] not in "\r\n":
                masked[position] = " "
    return "".join(masked)


def _delimiter_pairs(tokens: list[str]) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    closing = {")": "(", "]": "[", "}": "{"}
    for i, token in enumerate(tokens):
        if token in {"(", "[", "{"}:
            stack.append(i)
        elif token in closing:
            if stack and tokens[stack[-1]] == closing[token]:
                opening = stack.pop()
                pairs[opening] = i
                pairs[i] = opening
            else:
                # Avoid treating mismatched delimiters as a valid header.
                stack.clear()
    return pairs


def _is_braced_do_tail(tokens: list[str], index: int, pairs: dict[int, int]) -> bool:
    if index == 0 or tokens[index - 1] != "}":
        return False
    opening = pairs.get(index - 1, 0)
    return opening > 0 and tokens[opening - 1] == "do"


def _is_classic_case(tokens: list[str], index: int, pairs: dict[int, int]) -> bool:
    cursor = index + 1
    ternaries = 0
    while cursor < len(tokens):
        token = tokens[cursor]
        if token in {"(", "["} and cursor in pairs:
            cursor = pairs[cursor] + 1
            continue
        if token in {"->", ";", "{", "}", "case", "default"}:
            return False
        if token == "?":
            ternaries += 1
        elif token == ":":
            if not ternaries:
                return True
            ternaries -= 1
        cursor += 1
    return False


def java_rule_positions(text: str) -> dict[str, list[tuple[int, int]]]:
    """Return one-based keyword locations for two explicitly bounded rules.

    BRACES detects unbraced if/for/while/switch bodies. SWITCH identifies classic
    colon case labels for low-confidence informational review, including labels
    whose body already ends in break/return. Arrow rules are never such labels.
    """
    matches = list(_TOKEN.finditer(_mask_noncode(text)))
    tokens = [match.group() for match in matches]
    pairs = _delimiter_pairs(tokens)
    newlines = [-1, *[m.start() for m in re.finditer("\n", text)]]
    result: dict[str, list[tuple[int, int]]] = {BRACES: [], SWITCH: []}

    def location(index: int) -> tuple[int, int]:
        offset = matches[index].start()
        line = bisect_right(newlines, offset)
        return line, offset - newlines[line - 1]

    for index, token in enumerate(tokens):
        if token in {"if", "for", "while", "switch"}:
            opening = index + 1
            if opening >= len(tokens) or tokens[opening] != "(":
                continue
            closing = pairs.get(opening)
            if closing is None or closing + 1 >= len(tokens):
                continue
            if token == "while" and _is_braced_do_tail(tokens, index, pairs):
                continue
            if tokens[closing + 1] != "{":
                result[BRACES].append(location(index))
        elif token == "case" and _is_classic_case(tokens, index, pairs):
            result[SWITCH].append(location(index))
    return result
