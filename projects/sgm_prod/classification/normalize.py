from __future__ import annotations

import unicodedata


_KEEP_PUNCT = frozenset({"，", "、", ","})


def normalize_query(query: str) -> str:
    text = unicodedata.normalize("NFKC", query or "")
    return "".join(
        ch
        for ch in text
        if not ch.isspace()
        and (ch in _KEEP_PUNCT or not unicodedata.category(ch).startswith("P"))
    )
