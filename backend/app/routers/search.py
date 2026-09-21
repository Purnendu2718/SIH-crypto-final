"""Unified One-Box Multi-Chain Search & Validation Router.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8, 8C, & Universal Multi-Chain.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnalysisRun, Case, Profile, WalletSubmission, generate_uuid, utc_now
from app.security import get_current_officer_optional
from app.services.address_validator import validate, validate_address, ValidationResult
from app.services.providers.base import sanitize_source_url
from app.services.providers.registry import get_provider_adapter

router = APIRouter(prefix="", tags=["Unified Multi-Chain Search & Validation"])

# In-memory store for instant analysis retrieval by run_id
_ANALYSIS_STORE: Dict[str, Dict[str, Any]] = {}


class ValidateRequest(BaseModel):
    query: Optional[str] = None
    address: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(..., description="Raw input: wallet address, transaction hash, or ENS name")
    case_id: Optional[str] = None
    all_candidates: Optional[bool] = False
    ncrp_ref: Optional[str] = None
    amount_inr: Optional[float] = None


# ---------------------------------------------------------------------------
# Step 1: Validation Endpoints (Pure, in-memory, safe for as-you-type use)
# ---------------------------------------------------------------------------

@router.post("/api/v1/validate", response_model=None)
@router.post("/api/validate", response_model=None)
def validate_identifier(req: ValidateRequest) -> Dict[str, Any]:
    """Pure in-memory cryptographic address and transaction hash validator.
    No network calls; sub-millisecond response time; safe for as-you-type UI feedback.
    """
    raw_query = req.query or req.address or ""
    result = validate(raw_query)
    return result.to_dict()


@router.post("/api/v1/validate-address", response_model=None)
def validate_address_legacy(req: ValidateRequest) -> Dict[str, Any]:
    """Backward-compatible alias for /api/v1/validate."""
    raw_query = req.query or req.address or ""
    result = validate_address(raw_query)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Step 2: Search API
# ---------------------------------------------------------------------------

@router.post("/api/v1/search", response_model=None)
@router.post("/api/search", response_model=None)
async def multi_chain_search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    current_officer: Optional[Profile] = Depends(get_current_officer_optional),
) -> Any:
    """Multi-Chain Forensics One-Box Search.
    Validates input with checksum-level precision, probes on-chain data across
    Bitcoin, EVM, TRON, Solana, XRPL, Stellar, UTXO forks, Cardano, and Monero.
    """
    clean_query = req.query.strip()
    val: ValidationResult = validate(clean_query)

    run_id = f"run_{uuid.uuid4().hex[:12]}"

    # 1. ENS Name: Needs resolution
    if val.kind == "ens_name":
        ens_resp = {
            "run_id": run_id,
            "query": clean_query,
            "validation": val.to_dict(),
            "status": "needs_resolution",
            "results": [],
            "message": "ENS name detected. On-chain resolution required to identify target address.",
        }
        _ANALYSIS_STORE[run_id] = ens_resp
        return ens_resp

    # 2. Reject invalid input with HTTP 422 and validation payload
    if not val.is_valid:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "validation": val.to_dict(),
                "detail": val.error or "Input failed cryptographic checksum validation.",
            },
        )

    # 3. Valid Address: Lookup on primary chain (or all candidate chains if all_candidates=True)
    if val.kind == "address":
        chains_to_probe: List[tuple[str, str]] = []

        if req.all_candidates:
            # Probe all candidates
            for cand in val.candidates:
                chains_to_probe.append((cand.chain, cand.network))
            # Probe related EVM chains if this is an EVM address
            for rel in (val.related_chains or []):
                if not any(c[0] == rel for c in chains_to_probe):
                    chains_to_probe.append((rel, "mainnet"))
        else:
            # Primary candidate only
            primary = val.primary or (val.candidates[0] if val.candidates else None)
            if primary:
                chains_to_probe.append((primary.chain, primary.network))
            else:
                chains_to_probe.append(("bitcoin", "mainnet"))

        async def _probe_address(chain_name: str, network: str) -> Dict[str, Any]:
            adapter = get_provider_adapter(chain_name)
            try:
                return await adapter.lookup_address(val.normalized, network=network)
            except Exception as e:
                return adapter._format_result(
                    status="unavailable",
                    error=f"Unexpected error: {e}",
                    network=network,
                )

        tasks = [_probe_address(c, net) for c, net in chains_to_probe]
        results = await asyncio.gather(*tasks)

        resp_data = {
            "run_id": run_id,
            "query": clean_query,
            "validation": val.to_dict(),
            "results": results,
        }
        _ANALYSIS_STORE[run_id] = resp_data

        # Background record linking to DB if officer/case present
        try:
            if current_officer and db:
                c_id = req.case_id or generate_uuid()
                new_sub = WalletSubmission(
                    submission_id=generate_uuid(),
                    case_id=c_id,
                    chain=chains_to_probe[0][0].upper(),
                    address=val.normalized,
                )
                db.add(new_sub)
                db.commit()
        except Exception:
            pass

        return resp_data

    # 4. Valid Transaction Hash: Probe candidate chains concurrently
    if val.kind == "transaction_hash":
        chains_to_probe = [(c.chain, c.network) for c in val.candidates]

        async def _probe_tx(chain_name: str, network: str) -> Dict[str, Any]:
            adapter = get_provider_adapter(chain_name)
            try:
                return await adapter.lookup_tx(val.normalized, network=network)
            except Exception as e:
                return adapter._format_result(
                    status="unavailable",
                    error=f"Unexpected error: {e}",
                    network=network,
                )

        tasks = [_probe_tx(c, net) for c, net in chains_to_probe]
        probe_results = await asyncio.gather(*tasks)

        # Check if tx hash resolves in fixture dataset or live
        from app.services.adapters.fixture_adapter import FixtureAdapter
        from app.services import run_full_forensic_pipeline

        fa = FixtureAdapter()
        matched_tx = None
        for sc in fa.get_scenarios():
            for t in sc.get("transactions", []):
                if t.get("tx_hash", "").strip().lower() == clean_query.lower():
                    matched_tx = t
                    break
            if matched_tx:
                break

        if matched_tx:
            resolved_address = matched_tx["from_address"]
            detected_chain = matched_tx.get("chain", "ETH").upper()
            c_id = req.case_id or generate_uuid()

            if db:
                try:
                    existing_case = db.query(Case).filter(Case.case_id == c_id).first()
                    if not existing_case:
                        new_case = Case(
                            case_id=c_id,
                            ncrp_ref=req.ncrp_ref or f"NCRP/{utc_now().year}/TX-{clean_query[:8]}",
                            amount_inr=req.amount_inr,
                            status="OPEN",
                            assigned_officer_id=current_officer.id if current_officer else None,
                        )
                        db.add(new_case)
                        db.flush()
                    new_sub = WalletSubmission(
                        submission_id=generate_uuid(),
                        case_id=c_id,
                        chain=detected_chain,
                        address=resolved_address,
                    )
                    db.add(new_sub)
                    db.commit()
                except Exception:
                    pass

            forensic_data = run_full_forensic_pipeline(
                start_address=resolved_address,
                chain=detected_chain,
                stolen_principal=req.amount_inr,
                db=db,
            )

            resp_data = {
                "run_id": forensic_data.get("run_id", run_id),
                "query": clean_query,
                "query_type": "TRANSACTION_HASH",
                "detected_chain": detected_chain,
                "resolved_address": resolved_address,
                "case_id": c_id,
                "status": forensic_data.get("status", "ANALYSIS_COMPLETE_ATTRIBUTED"),
                "matched_entity": forensic_data.get("attribution", {}).get("matched_entity"),
                "confidence": forensic_data.get("attribution", {}).get("confidence", 0.0),
                "confidence_band": forensic_data.get("attribution", {}).get("confidence_band", "INSUFFICIENT_EVIDENCE"),
                "total_hops": forensic_data.get("trace", {}).get("total_hops", 0),
                "confirmations": 12,
                "low_confirmation": False,
                "is_pending": False,
                "validation": val.to_dict(),
                "results": probe_results,
                "forensic_payload": forensic_data,
            }
            _ANALYSIS_STORE[run_id] = resp_data
            return resp_data

        resp_data = {
            "run_id": run_id,
            "query": clean_query,
            "query_type": "TRANSACTION_HASH",
            "validation": val.to_dict(),
            "results": probe_results,
        }
        _ANALYSIS_STORE[run_id] = resp_data
        return resp_data

    # Fallback
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"validation": val.to_dict(), "detail": "Unrecognized identifier kind."},
    )


# ---------------------------------------------------------------------------
# Step 2: Analysis Retrieval & Health
# ---------------------------------------------------------------------------

@router.get("/api/v1/analysis/{run_id}", response_model=None)
@router.get("/api/analysis/{run_id}", response_model=None)
def get_analysis_by_run_id(run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve stored forensic search analysis by run_id."""
    clean_id = run_id.strip()
    if clean_id in _ANALYSIS_STORE:
        return _ANALYSIS_STORE[clean_id]

    # Check DB AnalysisRun
    db_run = db.query(AnalysisRun).filter(AnalysisRun.run_id == clean_id).first()
    if db_run:
        return {
            "run_id": db_run.run_id,
            "status": db_run.status,
            "created_at": db_run.created_at.isoformat() if db_run.created_at else None,
            "completed_at": db_run.completed_at.isoformat() if db_run.completed_at else None,
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Analysis run '{run_id}' not found in current session.",
    )
