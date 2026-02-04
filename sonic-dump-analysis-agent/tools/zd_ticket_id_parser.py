import re
from typing import Any, Dict, List

from ncp import tool


@tool
def zd_ticket_id_parser(text: str) -> Dict[str, Any]:
    """
    Parse ticket IDs and ranges from free-form text.

    Input examples:
        "1502,1400-1402,999"
        "1502,1400-1402,999 also 800-850"

    Output:
        {
          "input": "<original text>",
          "ids": [999, 1400, 1401, 1402, 1502, 800, ..., 850],
          "success": true/false,
          "error": null or error message
        }

    The agent MUST use this tool whenever the user specifies ticket IDs
    or ranges in free-form text (with commas, dashes, 'also', etc.)
    and MUST NOT attempt to parse IDs manually.
    """
    text = (text or "").strip()
    if not text:
        return {"input": text, "ids": [], "success": False, "error": "No input provided."}

    tokens = re.split(r"[,\s;]+", text)
    ids: List[int] = []

    for tok in tokens:
        if not tok:
            continue
        if "-" in tok:
            parts = tok.split("-", 1)
            try:
                start = int(parts[0])
                end = int(parts[1])
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            ids.extend(range(start, end + 1))
        else:
            try:
                ids.append(int(tok))
            except ValueError:
                continue

    ids = sorted(set(ids))

    if not ids:
        return {
            "input": text,
            "ids": [],
            "success": False,
            "error": "No valid ticket IDs found.",
        }

    return {
        "input": text,
        "ids": ids,
        "success": True,
        "error": None,
    }