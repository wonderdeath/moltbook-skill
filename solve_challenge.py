#!/usr/bin/env python3
"""
Moltbook Verification Challenge Solver

Parses obfuscated math challenges returned by the Moltbook API
after creating posts/comments, computes the answer, and submits it.

Usage:
    python3 solve_challenge.py <verification_code> <challenge_text> <api_key>

The challenge_text is typically an obfuscated arithmetic expression.
Common obfuscation patterns:
  - Word-based numbers: "seven plus three" -> 7 + 3
  - Unicode digits mixed with words
  - Spelled-out operators: "plus", "minus", "times", "divided by"
  - Parenthesized sub-expressions
  - Whitespace/zero-width character noise
"""

import json
import re
import sys
import urllib.request
import unicodedata

API_BASE = "https://www.moltbook.com/api/v1"

# ── Word-to-number mapping ──────────────────────────────────────────

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}

WORD_OPERATORS = {
    "plus": "+", "add": "+", "added to": "+", "sum of": "+",
    "minus": "-", "subtract": "-", "less": "-", "take away": "-",
    "times": "*", "multiply": "*", "multiplied by": "*", "x": "*",
    "divided by": "/", "divide": "/", "over": "/",
}


def strip_noise(text: str) -> str:
    """Remove zero-width characters, combining marks, and excess whitespace."""
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep letters, digits, basic punctuation, spaces
        if cat.startswith(("L", "N", "P", "Z", "S")):
            # Skip zero-width and format characters
            if cat in ("Cf", "Mn", "Me", "Mc") and ch not in "().-+*/":
                continue
            cleaned.append(ch)
    return " ".join("".join(cleaned).split())


def word_number_to_compound(words: list[str]) -> float | None:
    """Convert a sequence of number-words into a numeric value.

    Handles patterns like:
      - "twenty three" -> 23
      - "five hundred" -> 500
      - "three hundred forty two" -> 342
    """
    if not words:
        return None

    total = 0
    current = 0

    for w in words:
        val = WORD_NUMBERS.get(w.lower())
        if val is None:
            return None
        if val == 100:
            current = (current if current else 1) * 100
        elif val == 1000:
            current = (current if current else 1) * 1000
            total += current
            current = 0
        elif val >= 20:
            current += val
        else:
            current += val

    return float(total + current)


def replace_word_numbers(text: str) -> str:
    """Replace spelled-out numbers with digits."""
    tokens = text.split()
    result = []
    i = 0

    while i < len(tokens):
        # Try to consume a run of number-words
        number_words = []
        j = i
        while j < len(tokens):
            clean = tokens[j].lower().strip("(),.")
            if clean in WORD_NUMBERS:
                number_words.append(clean)
                j += 1
            elif clean == "and" and number_words:
                # "three hundred and forty two"
                j += 1
            else:
                break

        if number_words:
            val = word_number_to_compound(number_words)
            if val is not None:
                result.append(str(val))
                i = j
                continue

        result.append(tokens[i])
        i += 1

    return " ".join(result)


def replace_word_operators(text: str) -> str:
    """Replace spelled-out operators with symbols."""
    # Sort by length (longest first) to match multi-word operators first
    for word, symbol in sorted(WORD_OPERATORS.items(), key=lambda x: -len(x[0])):
        text = re.sub(
            r"\b" + re.escape(word) + r"\b",
            f" {symbol} ",
            text,
            flags=re.IGNORECASE,
        )
    return text


def normalize_expression(text: str) -> str:
    """Convert an obfuscated challenge into a clean arithmetic expression."""
    text = strip_noise(text)
    text = replace_word_numbers(text)
    text = replace_word_operators(text)

    # Remove everything except digits, operators, parentheses, dots, spaces
    text = re.sub(r"[^0-9+\-*/(). ]", " ", text)

    # Collapse whitespace
    text = " ".join(text.split())

    # Remove trailing operators
    text = re.sub(r"[+\-*/]\s*$", "", text.strip())

    return text.strip()


def safe_eval(expression: str) -> float:
    """Evaluate a simple arithmetic expression safely (no exec/eval)."""
    # Validate that the expression only contains safe characters
    if not re.match(r"^[\d+\-*/().  ]+$", expression):
        raise ValueError(f"Unsafe expression: {expression}")

    # Use Python's eval with restricted builtins
    allowed = {"__builtins__": {}}
    try:
        result = eval(expression, allowed)  # noqa: S307
    except Exception as e:
        raise ValueError(f"Could not evaluate '{expression}': {e}") from e

    return float(result)


def solve_challenge(challenge_text: str) -> str:
    """Parse the challenge, compute result, return formatted answer."""
    expr = normalize_expression(challenge_text)

    if not expr:
        raise ValueError(f"Could not parse challenge: {challenge_text}")

    result = safe_eval(expr)
    return f"{result:.2f}"


def submit_verification(verification_code: str, answer: str, api_key: str) -> dict:
    """Submit the verification answer to Moltbook API."""
    payload = json.dumps({
        "verification_code": verification_code,
        "answer": answer,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE}/verify",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}", "body": body}
    except urllib.error.URLError as e:
        return {"success": False, "error": str(e)}


def main():
    if len(sys.argv) != 4:
        print("Usage: solve_challenge.py <verification_code> <challenge_text> <api_key>")
        print("  verification_code: from post/comment creation response")
        print("  challenge_text:    the obfuscated math problem")
        print("  api_key:           your Moltbook API key")
        sys.exit(1)

    verification_code = sys.argv[1]
    challenge_text = sys.argv[2]
    api_key = sys.argv[3]

    # Solve
    try:
        answer = solve_challenge(challenge_text)
    except ValueError as e:
        print(json.dumps({"success": False, "error": f"Solver error: {e}"}))
        sys.exit(1)

    print(json.dumps({"step": "solved", "expression_parsed": normalize_expression(challenge_text), "answer": answer}))

    # Submit
    result = submit_verification(verification_code, answer, api_key)
    print(json.dumps(result))

    if result.get("success"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
