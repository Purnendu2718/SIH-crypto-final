"""Known entities registry and loader.
Single source of truth for verified manual attributions.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_KNOWN_ENTITIES: List[Dict[str, Any]] = []
_LOADED = False


def _load_known_entities() -> None:
    global _KNOWN_ENTITIES, _LOADED
    if _LOADED:
        return

    possible_paths = [
        os.path.join(os.getcwd(), "data", "known_entities.json"),
        os.path.join(os.getcwd(), "backend", "data", "known_entities.json"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "known_entities.json")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "known_entities.json")),
    ]

    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        _KNOWN_ENTITIES = data
                        _LOADED = True
                        return
            except Exception:
                continue

    _LOADED = True


def get_known_entity_labels(address: str, chain: str) -> List[Dict[str, Any]]:
    """Returns matching labels for an address and chain from known_entities.json."""
    _load_known_entities()
    if not address:
        return []

    clean_addr = address.strip()
    is_evm = chain.lower() in ("ethereum", "polygon", "arbitrum", "optimism", "bsc", "base", "avalanche", "eth")

    matches: List[Dict[str, Any]] = []
    for item in _KNOWN_ENTITIES:
        target_addr = item.get("address", "").strip()
        target_chain = item.get("chain", "").lower()

        # Chain matching
        if target_chain != "all" and target_chain != chain.lower():
            continue

        # Address matching: case-insensitive for EVM, exact for base58/others
        if is_evm:
            matched = clean_addr.lower() == target_addr.lower()
        else:
            matched = clean_addr == target_addr

        if matched:
            label_text = item.get("label", "")
            desc = item.get("description", "")
            full_label = f"{label_text} — {desc}" if desc and desc not in label_text else label_text
            matches.append({
                "label": full_label,
                "source": item.get("source", "known_entities"),
                "confidence": float(item.get("confidence", 1.0)),
            })

    return matches
