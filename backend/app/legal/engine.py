"""Deterministic Legal Mapping Engine.
Maps cybercrime typologies to statutory penal provisions under BNS, IPC, IT Act 2000, and PMLA 2002.
Reference: Phase 8 — Legal mapping engine, Ministry of Home Affairs / I4C.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date
import yaml


TRANSITION_DATE = "2024-07-01"
MANDATORY_DISCLAIMER = (
    "Suggestions for review by the investigating officer and legal counsel; "
    "verify each section on indiacode.nic.in."
)

DEFAULT_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.yaml")

VALID_SOURCES = {"complaint", "on_chain", "officer"}
VALID_SIGNALS = {
    "cycle_detected",
    "multi_hop_layering",
    "mixer_exposure",
    "sanctioned_exposure",
    "exchange_endpoint",
    "peel_chain",
}


def load_rules(filepath: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate rules YAML file. Fails on malformed or schema-invalid data."""
    path = filepath or DEFAULT_RULES_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Rules YAML file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Malformed YAML in rules file: {e}")

    if not isinstance(data, dict):
        raise ValueError("Rules YAML must be a top-level dictionary.")

    # Validate required top-level keys
    for req_key in ["rules_version", "disclaimer", "provisions", "typologies"]:
        if req_key not in data:
            raise ValueError(f"Rules YAML missing required top-level key: '{req_key}'")

    provisions = data["provisions"]
    if not isinstance(provisions, dict) or not provisions:
        raise ValueError("'provisions' must be a non-empty dictionary.")

    for p_id, p_data in provisions.items():
        if not isinstance(p_data, dict):
            raise ValueError(f"Provision '{p_id}' must be a dictionary.")
        for field in ["act", "section", "title", "ipc_equivalent", "verified", "verify_at"]:
            if field not in p_data:
                raise ValueError(f"Provision '{p_id}' is missing required field '{field}'.")
        if not isinstance(p_data["verified"], bool):
            raise ValueError(f"Provision '{p_id}' field 'verified' must be a boolean.")
        if p_data["verify_at"] != "https://indiacode.nic.in":
            raise ValueError(f"Provision '{p_id}' verify_at must point to 'https://indiacode.nic.in'.")

    typologies = data["typologies"]
    if not isinstance(typologies, dict) or not typologies:
        raise ValueError("'typologies' must be a non-empty dictionary.")

    for typo_id, typo_data in typologies.items():
        if not isinstance(typo_data, dict):
            raise ValueError(f"Typology '{typo_id}' must be a dictionary.")
        if "provisions" not in typo_data or not isinstance(typo_data["provisions"], list):
            raise ValueError(f"Typology '{typo_id}' must contain a list of 'provisions'.")
        for prov_ref in typo_data["provisions"]:
            if prov_ref not in provisions:
                raise ValueError(f"Typology '{typo_id}' references unknown provision '{prov_ref}'.")

        if "checklist" not in typo_data or not isinstance(typo_data["checklist"], list):
            raise ValueError(f"Typology '{typo_id}' must contain an ingredients 'checklist'.")

        for idx, item in enumerate(typo_data["checklist"]):
            if not isinstance(item, dict):
                raise ValueError(f"Checklist item {idx} in typology '{typo_id}' must be a dict.")
            for req_field in ["ingredient", "source"]:
                if req_field not in item:
                    raise ValueError(f"Checklist item {idx} in '{typo_id}' missing '{req_field}'.")
            if item["source"] not in VALID_SOURCES:
                raise ValueError(f"Invalid source '{item['source']}' in checklist item {idx} of '{typo_id}'.")
            sig = item.get("signal")
            if sig is not None and sig not in VALID_SIGNALS:
                raise ValueError(f"Invalid signal '{sig}' in checklist item {idx} of '{typo_id}'.")

    return data


class LegalRulesEngine:
    """Deterministic rules evaluation engine for Indian cybercrime penal provisions."""

    def __init__(self, rules_data: Optional[Dict[str, Any]] = None):
        self.rules = rules_data if rules_data is not None else load_rules()
        self.rules_version = self.rules.get("rules_version", "1.0.0")
        self.disclaimer = self.rules.get("disclaimer", MANDATORY_DISCLAIMER)

    def evaluate_signals(self, trace_result: Optional[Dict[str, Any]] = None) -> Dict[str, Tuple[bool, str]]:
        """Evaluate on-chain signals from stored case trace result."""
        signals: Dict[str, Tuple[bool, str]] = {}
        tr = trace_result or {}

        paths = tr.get("paths", [])
        cycles = tr.get("cycles", [])
        typos = [t.get("typology") if isinstance(t, dict) else str(t) for t in tr.get("typologies", [])]

        # 1. cycle_detected
        has_cycle = (
            bool(tr.get("cycle_detected"))
            or (isinstance(cycles, list) and len(cycles) > 0)
            or any(p.get("inCycle") or p.get("in_cycle") for p in paths if isinstance(p, dict))
        )
        if not has_cycle and isinstance(paths, list) and len(paths) > 0:
            adj: Dict[str, List[str]] = {}
            for p in paths:
                if isinstance(p, dict):
                    u = p.get("from") or p.get("from_addr")
                    v = p.get("to") or p.get("to_addr")
                    if u and v:
                        adj.setdefault(str(u), []).append(str(v))
            visited: Dict[str, int] = {}
            def dfs(node: str) -> bool:
                visited[node] = 1  # visiting
                for nxt in adj.get(node, []):
                    if visited.get(nxt) == 1:
                        return True
                    if visited.get(nxt) is None:
                        if dfs(nxt):
                            return True
                visited[node] = 2  # visited
                return False
            for node in list(adj.keys()):
                if node not in visited:
                    if dfs(node):
                        has_cycle = True
                        break

        signals["cycle_detected"] = (
            has_cycle,
            f"{len(cycles) if cycles else 'Circular'} flow loop(s) detected in transaction graph."
            if has_cycle
            else "No circular flow loops identified.",
        )

        # 2. multi_hop_layering
        total_hops = tr.get("total_hops", len(paths))
        has_layering = (
            bool(tr.get("multi_hop_layering"))
            or total_hops > 2
            or "LAYERING" in typos
            or "FAN_OUT" in typos
        )
        signals["multi_hop_layering"] = (
            has_layering,
            f"Multi-hop fund flow observed ({total_hops} hops) with layering characteristics."
            if has_layering
            else "Direct or single-hop movement.",
        )

        # 3. mixer_exposure
        has_mixer = (
            bool(tr.get("mixer_exposure"))
            or "MIXER" in typos
            or any(
                (p.get("heuristicBadge") == "MIXER" or "mixer" in str(p.get("category", "")).lower() or "tornado" in str(p.get("label", "")).lower())
                for p in paths
                if isinstance(p, dict)
            )
        )
        signals["mixer_exposure"] = (
            has_mixer,
            "On-chain interaction with privacy mixer or tumbler protocol detected."
            if has_mixer
            else "No mixer interaction identified.",
        )

        # 4. sanctioned_exposure
        has_sanctioned = (
            bool(tr.get("sanctioned_exposure"))
            or any(
                ("sanction" in str(p.get("category", "")).lower() or "ofac" in str(p.get("label", "")).lower())
                for p in paths
                if isinstance(p, dict)
            )
        )
        signals["sanctioned_exposure"] = (
            has_sanctioned,
            "Transfer path intersects flagged or sanctioned wallet infrastructure."
            if has_sanctioned
            else "No sanctioned exposure detected.",
        )

        # 5. exchange_endpoint
        reached_vasp = (
            bool(tr.get("exchange_endpoint"))
            or bool(tr.get("reached_vasp"))
            or bool(tr.get("vasp_name"))
        )
        vasp_name = tr.get("vasp_name") or "VASP"
        signals["exchange_endpoint"] = (
            reached_vasp,
            f"Funds traced to destination exchange/VASP deposit infrastructure ({vasp_name})."
            if reached_vasp
            else "No attributed VASP endpoint identified.",
        )

        # 6. peel_chain
        has_peel = bool(tr.get("peel_chain")) or "PEELING_CHAIN" in typos
        signals["peel_chain"] = (
            has_peel,
            "Peeling chain structured consolidation detected."
            if has_peel
            else "No peeling chain pattern detected.",
        )

        return signals

    def evaluate_date_scheme(self, offence_date_input: Optional[Any]) -> Tuple[str, str, Optional[str]]:
        """Determine whether IPC, BNS, or BOTH applies based on 2024-07-01 boundary."""
        if not offence_date_input or (isinstance(offence_date_input, str) and not offence_date_input.strip()):
            return (
                "BOTH",
                "Offence date not specified. Since BNS replaced IPC on 1 July 2024, the offence date determines whether IPC (prior to 1 July 2024) or BNS (from 1 July 2024) applies. Both statutory mappings are provided below for review.",
                None,
            )

        parsed_date_str = None
        if isinstance(offence_date_input, (datetime, date)):
            parsed_date_str = offence_date_input.strftime("%Y-%m-%d")
        elif isinstance(offence_date_input, str):
            clean_str = offence_date_input.strip()
            match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", clean_str)
            if match:
                parsed_date_str = match.group(0)
            else:
                try:
                    dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
                    parsed_date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    parsed_date_str = None

        if not parsed_date_str:
            return (
                "BOTH",
                "Unable to parse offence date. Since BNS replaced IPC on 1 July 2024, the offence date determines which code applies. Both statutory mappings are provided below for review.",
                None,
            )


        if parsed_date_str < TRANSITION_DATE:
            return (
                "IPC",
                f"Offence date ({parsed_date_str}) is prior to 1 July 2024. Indian Penal Code (IPC) applies as the primary substantive criminal law.",
                parsed_date_str,
            )
        else:
            return (
                "BNS",
                f"Offence date ({parsed_date_str}) is on or after 1 July 2024. Bharatiya Nyaya Sanhita (BNS) applies as the primary substantive criminal law.",
                parsed_date_str,
            )

    def suggest_provisions(
        self,
        typology: str,
        offence_date: Optional[Any] = None,
        trace_result: Optional[Dict[str, Any]] = None,
        case_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate structured legal suggestions for a given typology and case."""
        typologies = self.rules.get("typologies", {})
        if typology not in typologies:
            available = list(typologies.keys())
            raise ValueError(f"Unknown typology '{typology}'. Available typologies: {available}")

        typo_meta = typologies[typology]
        all_provisions = self.rules.get("provisions", {})

        scheme, scheme_note, formatted_offence_date = self.evaluate_date_scheme(offence_date)
        signals = self.evaluate_signals(trace_result)

        # Build formatted provisions
        provisions_output = []
        for prov_id in typo_meta.get("provisions", []):
            prov = all_provisions.get(prov_id)
            if not prov:
                continue

            act = prov.get("act", "")
            section = prov.get("section", "")
            title = prov.get("title", "")
            ipc_equiv = prov.get("ipc_equivalent")
            verified = prov.get("verified", False)
            badge = "Cross-checked" if verified else "Unverified"
            verify_at = prov.get("verify_at", "https://indiacode.nic.in")
            notes = prov.get("notes")

            if scheme == "IPC":
                if ipc_equiv:
                    primary_disp = f"{ipc_equiv}: {title}"
                    secondary_disp = f"Corresponding BNS Section: {act} {section}"
                else:
                    primary_disp = f"{act} {section}: {title}"
                    secondary_disp = "No direct IPC equivalent (Special / New Law)"
            elif scheme == "BNS":
                primary_disp = f"{act} {section}: {title}"
                secondary_disp = f"Erstwhile IPC Equivalent: {ipc_equiv}" if ipc_equiv else "New Statutory Offence (No IPC equivalent)"
            else:  # BOTH
                primary_disp = f"{act} {section} / {ipc_equiv or 'No IPC'}: {title}"
                secondary_disp = "Offence date required to finalize substantive code"

            provisions_output.append({
                "id": prov_id,
                "act": act,
                "section": section,
                "title": title,
                "primary_display": primary_disp,
                "secondary_display": secondary_disp,
                "ipc_equivalent": ipc_equiv,
                "verified": verified,
                "badge": badge,
                "verify_at": verify_at,
                "notes": notes,
            })

        # Evaluate ingredients checklist
        case_info = case_data or {}
        has_complaint_info = bool(case_info.get("victim_utr") or case_info.get("ncrp_ref") or case_info.get("amount_inr"))

        checklist_output = []
        for item in typo_meta.get("checklist", []):
            ingredient = item.get("ingredient", "")
            source = item.get("source", "officer")
            sig_name = item.get("signal")

            if source == "on_chain" and sig_name:
                present, detail_msg = signals.get(sig_name, (False, "Signal not observed"))
                status = "present" if present else "missing"
                details = detail_msg
            elif source == "complaint":
                status = "present" if has_complaint_info else "needs_officer_input"
                details = "Supported by complainant reporting." if has_complaint_info else "Requires victim statement or bank UTR verification."
            else:
                status = "needs_officer_input"
                details = "Requires investigating officer field inquiry or forensic attestation."

            checklist_output.append({
                "ingredient": ingredient,
                "source": source,
                "signal": sig_name,
                "status": status,
                "details": details,
            })

        return {
            "rules_version": self.rules_version,
            "disclaimer": self.disclaimer,
            "typology": typology,
            "typology_title": typo_meta.get("title", typology),
            "offence_date": formatted_offence_date,
            "scheme": scheme,
            "scheme_note": scheme_note,
            "provisions": provisions_output,
            "ingredients_checklist": checklist_output,
        }
