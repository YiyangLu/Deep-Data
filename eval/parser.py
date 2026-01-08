"""Parse agent responses for iPlotBench evaluation.

Extract figure JSON and yes/no answers from text responses.
"""

import json
import re
from typing import Optional


def parse_figure(text: str) -> dict:
    """
    Extract Plotly figure JSON from agent response text.

    Looks for {"data": [...], "layout": {...}} pattern.
    Returns empty dict if not found or invalid.
    """
    if not text:
        return {}

    # Try to find JSON with "data" key
    # Strategy: find all potential JSON objects and check for "data" key

    # First, try to find JSON code block
    code_block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if isinstance(data, dict) and "data" in data:
                return data
        except json.JSONDecodeError:
            pass

    # Find all potential JSON objects (matching braces)
    # Start from positions where we see {"data" or { "data"
    for match in re.finditer(r'\{[\s]*"data"', text):
        start = match.start()
        # Find matching closing brace
        depth = 0
        end = start
        for i, char in enumerate(text[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end > start:
            try:
                candidate = text[start:end]
                data = json.loads(candidate)
                if isinstance(data, dict) and "data" in data:
                    return data
            except json.JSONDecodeError:
                continue

    # Fallback: try first { to last }
    try:
        start = text.index('{')
        end = text.rindex('}') + 1
        data = json.loads(text[start:end])
        if isinstance(data, dict) and "data" in data:
            return data
    except (ValueError, json.JSONDecodeError):
        pass

    return {}


def parse_answer(text: str) -> Optional[int]:
    """
    Extract 0/1 answer from agent response text.

    Looks for 0 or 1 in the response.
    Returns None if not found or ambiguous.
    """
    if not text:
        return None

    text = text.strip()

    # Check for exact "0" or "1" response
    if text == "0":
        return 0
    if text == "1":
        return 1

    # Check for "Answer: 0" or "Answer: 1" pattern
    answer_match = re.search(r'(?:answer|response)[\s:]*([01])\b', text, re.IGNORECASE)
    if answer_match:
        return int(answer_match.group(1))

    # Check for standalone 0 or 1 (word boundary)
    # Prefer last occurrence (likely the final answer)
    zeros = list(re.finditer(r'\b0\b', text))
    ones = list(re.finditer(r'\b1\b', text))

    # If only one type found, use it
    if zeros and not ones:
        return 0
    if ones and not zeros:
        return 1

    # If both found, use the last one
    if zeros and ones:
        last_zero = zeros[-1].start()
        last_one = ones[-1].start()
        return 0 if last_zero > last_one else 1

    # Check for yes/no
    text_lower = text.lower()
    if re.search(r'\byes\b', text_lower):
        return 1
    if re.search(r'\bno\b', text_lower):
        return 0

    return None
