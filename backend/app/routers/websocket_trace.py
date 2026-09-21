"""WebSocket Trace Streaming Router.
Streams trace hops sequentially to enable live, animated graph rendering in the frontend.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Case, WalletSubmission, AnalysisRun, TracePath, Attribution
from app.services.trace_engine import TraceEngine
from app.services.attribution import AttributionEngine
from app.services.bridge_detector import detect_bridge_hop

logger = logging.getLogger("sentinel.ws_trace")

router = APIRouter(prefix="/api/ws", tags=["WebSocket Trace"])


@router.websocket("/trace/{identifier}")
async def stream_trace_by_submission(websocket: WebSocket, identifier: str):
    """Stream hops for a specific wallet submission, case, or run hop-by-hop."""
    await websocket.accept()
    db: Session = SessionLocal()

    try:
        # 1. Resolve target submission from identifier (can be submission_id, case_id, or run_id)
        submission = db.query(WalletSubmission).filter(WalletSubmission.submission_id == identifier).first()
        if not submission:
            submission = db.query(WalletSubmission).filter(WalletSubmission.case_id == identifier).first()
        if not submission:
            run_obj = db.query(AnalysisRun).filter(AnalysisRun.run_id == identifier).first()
            if run_obj:
                submission = db.query(WalletSubmission).filter(WalletSubmission.submission_id == run_obj.submission_id).first()

        if not submission:
            await websocket.send_json({
                "type": "ERROR",
                "message": f"Target entity '{identifier}' not found.",
            })
            await websocket.close()
            return

        run = db.query(AnalysisRun).filter(AnalysisRun.submission_id == submission.submission_id).first()
        if not run:
            # Execute trace engine on demand if no run exists yet
            engine = TraceEngine()
            result = engine.execute_trace(submission.address, submission.chain, db=db)
            hops = result.paths
            vasp_match = result.matched_entity
            run_status = result.status
            attrib = None
        else:
            paths = db.query(TracePath).filter(TracePath.run_id == run.run_id).order_by(TracePath.hop_index.asc()).all()
            hops = paths
            attrib = db.query(Attribution).filter(Attribution.run_id == run.run_id).first()
            vasp_match = attrib.matched_entity if attrib else None
            run_status = run.status

            if not vasp_match and hops:
                engine = TraceEngine()
                vasp_map = engine._get_vasp_hot_wallet_map(db)
                to_addr = getattr(hops[-1], "to_addr", None) or getattr(hops[-1], "to_address", "")
                vasp_match = vasp_map.get(to_addr.strip().lower())

        # 2. Send initialization event
        await websocket.send_json({
            "type": "TRACE_STARTED",
            "submission_id": submission.submission_id,
            "start_address": submission.address,
            "chain": submission.chain,
            "total_hops": len(hops),
        })
        await asyncio.sleep(0.3)

        # 3. Stream hops sequentially
        for hop in hops:
            from_addr = getattr(hop, "from_addr", None) or getattr(hop, "from_address", "")
            to_addr = getattr(hop, "to_addr", None) or getattr(hop, "to_address", "")
            val = float(getattr(hop, "value", 0.0))
            tx_h = getattr(hop, "tx_hash", "")
            hop_idx = getattr(hop, "hop_index", 1)
            hop_chain = getattr(hop, "chain", submission.chain)

            # Phase 8 Freshness and confirmation indicators
            confs = getattr(hop, "confirmations", None)
            low_conf = getattr(hop, "low_confirmation", False)
            is_pend = getattr(hop, "is_pending", False)

            # Scoped cross-chain bridge detector
            bridge = detect_bridge_hop(to_address=to_addr, from_address=from_addr, value=val)

            payload = {
                "type": "HOP_DISCOVERED",
                "hop_index": hop_idx,
                "from_addr": from_addr,
                "to_addr": to_addr,
                "value": val,
                "tx_hash": tx_h,
                "chain": hop_chain,
                "confirmations": confs,
                "low_confirmation": low_conf,
                "is_pending": is_pend,
                "is_bridge": bridge is not None,
                "bridge_details": bridge.model_dump() if bridge else None,
            }
            await websocket.send_json(payload)
            await asyncio.sleep(0.35)  # Pace frames for smooth UI animations

        # 4. Send final attribution event
        attrib_info = None
        if attrib:
            attrib_info = {
                "matched_entity": attrib.matched_entity,
                "confidence": attrib.confidence,
                "confidence_band": attrib.confidence_band,
                "rule_fired": attrib.rule_fired,
            }

        await websocket.send_json({
            "type": "TRACE_COMPLETED",
            "status": run_status,
            "total_hops": len(hops),
            "matched_vasp": vasp_match,
            "attribution": attrib_info,
        })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for target {identifier}")
    except Exception as e:
        logger.exception(f"Error streaming trace hops: {e}")
        try:
            await websocket.send_json({"type": "ERROR", "message": str(e)})
        except Exception:
            pass
    finally:
        db.close()


@router.websocket("/trace-live")
async def stream_trace_live_query(websocket: WebSocket):
    """Interactive WebSocket endpoint where client sends address + chain to stream."""
    await websocket.accept()
    db: Session = SessionLocal()

    try:
        init_data = await websocket.receive_json()
        address = init_data.get("address", "").strip()
        chain = init_data.get("chain", "ETH").strip()

        if not address:
            await websocket.send_json({"type": "ERROR", "message": "Address is required."})
            await websocket.close()
            return

        engine = TraceEngine()
        result = engine.execute_trace(address, chain, db=db)

        await websocket.send_json({
            "type": "TRACE_STARTED",
            "start_address": address,
            "chain": chain,
            "total_hops": len(result.paths),
        })
        await asyncio.sleep(0.3)

        for hop in result.paths:
            from_a = getattr(hop, "from_addr", None) or getattr(hop, "from_address", "")
            to_a = getattr(hop, "to_addr", None) or getattr(hop, "to_address", "")
            val = float(getattr(hop, "value", 0.0))
            tx_h = getattr(hop, "tx_hash", "")
            idx = getattr(hop, "hop_index", 1)
            hop_chain = getattr(hop, "chain", chain)
            confs = getattr(hop, "confirmations", None)
            low_conf = getattr(hop, "low_confirmation", False)
            is_pend = getattr(hop, "is_pending", False)

            bridge = detect_bridge_hop(to_address=to_a, from_address=from_a, value=val)
            await websocket.send_json({
                "type": "HOP_DISCOVERED",
                "hop_index": idx,
                "from_addr": from_a,
                "to_addr": to_a,
                "value": val,
                "tx_hash": tx_h,
                "chain": hop_chain,
                "confirmations": confs,
                "low_confirmation": low_conf,
                "is_pending": is_pend,
                "is_bridge": bridge is not None,
                "bridge_details": bridge.model_dump() if bridge else None,
            })
            await asyncio.sleep(0.35)

        attrib_engine = AttributionEngine()
        attribution = attrib_engine.compute_attribution(
            run_id=result.run_id,
            paths=result.paths,
            matched_entity=result.matched_entity,
            matched_hot_wallet=result.matched_hot_wallet,
            db=db,
        )

        await websocket.send_json({
            "type": "TRACE_COMPLETED",
            "status": result.status,
            "total_hops": len(result.paths),
            "matched_vasp": result.matched_entity,
            "attribution": {
                "matched_entity": attribution.matched_entity,
                "confidence": attribution.confidence,
                "confidence_band": attribution.confidence_band,
                "rule_fired": attribution.rule_fired,
            },
        })

    except WebSocketDisconnect:
        logger.info("Live WebSocket client disconnected.")
    except Exception as e:
        logger.exception(f"Error in live WebSocket trace: {e}")
        try:
            await websocket.send_json({"type": "ERROR", "message": str(e)})
        except Exception:
            pass
    finally:
        db.close()
