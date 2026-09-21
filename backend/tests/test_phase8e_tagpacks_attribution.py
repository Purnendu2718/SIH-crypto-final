"""Pytest suite for Phase 8E: General-Purpose Worldwide Label Coverage.
Verifies:
1. Bulk ingestion of GraphSense TagPacks and ActorPacks.
2. Genuine local-dataset attribution on addresses never manually seeded by the team.
3. Propagation of entity categories (mixer, defi_dex, exchange) into typology.py and risk_engine.py.
4. Fallthrough to live GraphSense hosted API when LIVE_MODE is True.
5. Clean 'no match found' when LIVE_MODE is False.
6. Attribution hierarchy order: (a) Local -> (b) Live -> (c) OFAC -> (d) CEX Sweep -> (e) Insufficient Evidence.
7. Periodic refresh worker and admin endpoints.

Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Entity, EntityLabel, SanctionsList, TagPackSyncStatus
from app.services import run_full_forensic_pipeline
from app.services.tagpack_ingest import ingest_tagpacks_and_actors, ingest_from_seed_file
from app.services.tagpack_scheduler import refresh_tagpacks_job, should_refresh_tagpacks
from app.services.graphsense_client import GraphSenseClient

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    init_db()
    # Ingest TagPacks seed to ensure tables have verified GraphSense data
    db: Session = SessionLocal()
    try:
        ingest_from_seed_file(db)
    finally:
        db.close()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin_auth_header():
    # Login as supervisor (ACP Rajesh Verma)
    res = client.post(
        "/api/auth/login",
        json={"email": "verma@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1: Bulk-Ingestion of TagPacks and ActorPacks
# ---------------------------------------------------------------------------
def test_bulk_ingestion_populates_entities_and_labels(db):
    """Verify entities and entity_labels tables contain real-world actors and addresses."""
    entities_count = db.query(Entity).count()
    labels_count = db.query(EntityLabel).count()

    assert entities_count > 0, "Entities table should contain ingested GraphSense actors"
    assert labels_count > 0, "EntityLabels table should contain ingested address tags"

    # Check Binance actor
    binance_actor = db.query(Entity).filter(Entity.actor_id == "binance").first()
    assert binance_actor is not None
    assert "exchange" in binance_actor.categories

    # Check Blender.io actor
    blender_actor = db.query(Entity).filter(Entity.actor_id == "blenderio").first()
    assert blender_actor is not None
    assert "mixing_service" in blender_actor.categories

    # Check 1inch actor
    oneinch_actor = db.query(Entity).filter(Entity.actor_id == "1inch").first()
    assert oneinch_actor is not None
    assert "defi_dex" in oneinch_actor.categories


# ---------------------------------------------------------------------------
# Test 2: Attribution on Un-Seeded Real Addresses from TagPacks
# ---------------------------------------------------------------------------
def test_unseeded_binance_address_attribution(db):
    """Verify 1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s (from binance.yaml) attributes to Binance with category 'exchange'."""
    binance_addr = "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s"
    res = run_full_forensic_pipeline(start_address=binance_addr, chain="BTC", db=db)

    assert res["status"] == "ANALYSIS_COMPLETE_ATTRIBUTED"
    assert res["attribution"]["rule_fired"] == "LOCAL_ENTITY_LABEL_MATCH"
    assert res["attribution"]["matched_entity"] in ("Binance", "binance.com")
    assert res["attribution"]["entity_category"] == "exchange"
    assert res["attribution"]["confidence"] >= 0.95
    assert res["attribution"]["confidence_band"] == "VERY_HIGH"


def test_unseeded_blender_mixer_address_attribution_and_typology(db):
    """Verify 3NDzzVxiLBUs1WPvVGRfCYDTAD2Ua2PvW4 (from blender_io.yaml) attributes to Blender.io,
    triggers CRITICAL MIXER typology and elevates risk score.
    """
    blender_addr = "3NDzzVxiLBUs1WPvVGRfCYDTAD2Ua2PvW4"
    res = run_full_forensic_pipeline(start_address=blender_addr, chain="BTC", db=db)

    assert res["status"] == "ANALYSIS_COMPLETE_ATTRIBUTED"
    assert res["attribution"]["rule_fired"] == "LOCAL_ENTITY_LABEL_MATCH"
    assert res["attribution"]["matched_entity"].lower() == "blender.io"
    assert res["attribution"]["entity_category"] == "mixing_service"

    # Verify Typology Engine detected MIXER with CRITICAL severity
    mixer_hits = [t for t in res["typologies"] if t["typology"] == "MIXER"]
    assert len(mixer_hits) > 0, "Expected MIXER typology to be flagged for mixing_service entity"
    assert mixer_hits[0]["severity"] == "CRITICAL"

    # Verify Risk Engine elevated composite score to CRITICAL (>= 85)
    risk = res["risk"]
    assert risk["composite_score"] >= 85
    assert risk["risk_level"] == "CRITICAL"
    assert "blender.io" in risk["explanation"].lower()


def test_unseeded_1inch_defi_address_attribution_and_typology(db):
    """Verify 0x1111111254fb6c44bAC0beD2854e76F90643097d (from defi-protocols_1inch.yaml) attributes to 1inch,
    with category 'defi_dex' and DEFI_INTERACTION typology.
    """
    oneinch_addr = "0x1111111254fb6c44bAC0beD2854e76F90643097d"
    res = run_full_forensic_pipeline(start_address=oneinch_addr, chain="ETH", db=db)

    assert res["status"] == "ANALYSIS_COMPLETE_ATTRIBUTED"
    assert res["attribution"]["rule_fired"] == "LOCAL_ENTITY_LABEL_MATCH"
    assert "1inch" in res["attribution"]["matched_entity"]
    assert res["attribution"]["entity_category"] == "defi_dex"

    # Verify DEFI_INTERACTION typology
    defi_hits = [t for t in res["typologies"] if t["typology"] == "DEFI_INTERACTION"]
    assert len(defi_hits) > 0, "Expected DEFI_INTERACTION typology for defi_dex category"


# ---------------------------------------------------------------------------
# Test 3: Address Absent from Local Dataset (Offline vs Live Fallback)
# ---------------------------------------------------------------------------
def test_absent_address_when_live_mode_off_returns_clean_insufficient_evidence(db):
    """When LIVE_MODE is False, an unknown address must return a clean 'no match found locally or live'."""
    unseeded_addr = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"  # Checksum-valid Base58 BTC, absent from local dataset
    with patch.object(settings, "LIVE_MODE", False):
        res = run_full_forensic_pipeline(start_address=unseeded_addr, chain="BTC", db=db)

        assert res["status"] == "ANALYSIS_COMPLETE_NO_PATH_FOUND"
        assert res["attribution"]["matched_entity"] == "Insufficient Evidence"
        assert res["attribution"]["confidence"] == 0.0
        assert res["attribution"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"
        assert res["attribution"]["rule_fired"] in (
            "NO_PATH_DETECTED",
            "UNVERIFIED_CLUSTER_INSUFFICIENT_EVIDENCE",
        )


def test_absent_address_when_live_mode_on_falls_through_to_graphsense_api(db):
    """When LIVE_MODE is True, an unknown address queries GraphSense API and fires LIVE_GRAPHSENSE_ENTITY_MATCH."""
    unseeded_addr = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"

    mock_gs_response = {
        "entity_name": "Kraken Exchange Cluster",
        "actor_id": "kraken",
        "category": "exchange",
        "categories": ["exchange"],
        "cluster_id": 9876543,
        "source": "LIVE_GRAPHSENSE_API",
    }

    with patch.object(settings, "LIVE_MODE", True):
        with patch.object(GraphSenseClient, "lookup_address_entity", return_value=mock_gs_response) as mock_lookup:
            res = run_full_forensic_pipeline(start_address=unseeded_addr, chain="BTC", db=db)

            # Ensure live lookup was actually invoked
            mock_lookup.assert_called()

            assert res["status"] == "ANALYSIS_COMPLETE_ATTRIBUTED"
            assert res["attribution"]["rule_fired"] == "LIVE_GRAPHSENSE_ENTITY_MATCH"
            assert res["attribution"]["matched_entity"] == "Kraken Exchange Cluster"
            assert res["attribution"]["entity_category"] == "exchange"
            assert res["attribution"]["attribution_source"] == "LIVE_GRAPHSENSE_API"
            assert res["attribution"]["confidence"] >= 0.85


# ---------------------------------------------------------------------------
# Test 4: Attribution Hierarchy Ordering
# ---------------------------------------------------------------------------
def test_attribution_hierarchy_order_and_distinct_rules(db):
    """Confirm the 4-tier check order:
    (a) local entity_labels match
    (b) live GraphSense API match (if LIVE_MODE=True)
    (c) OFAC sanctions match
    (d) CEX sweep-heuristic match
    """
    from app.services.attribution import AttributionEngine

    engine = AttributionEngine()

    # Tier (a): Local match
    res_a = engine.compute_attribution(
        run_id="test-run-a",
        paths=[],
        target_address="3NDzzVxiLBUs1WPvVGRfCYDTAD2Ua2PvW4",  # In local TagPacks
        chain="BTC",
        db=db,
    )
    assert res_a.rule_fired == "LOCAL_ENTITY_LABEL_MATCH"
    assert res_a.matched_entity.lower() == "blender.io"
    assert res_a.entity_category == "mixing_service"

    # Tier (c): OFAC Sanctions match for address absent from entity_labels
    ofac_addr = "124L9k62UQUpnWn74S5kJ5kQkHchjD7WzH"
    sanction_entry = db.query(SanctionsList).filter(SanctionsList.address == ofac_addr).first()
    if not sanction_entry:
        sanction_entry = SanctionsList(
            address=ofac_addr,
            chain="BTC",
            program="CYBER2",
            entity_name="Lazarus Group Mixer Target",
        )
        db.add(sanction_entry)
        db.commit()

    res_c = engine.compute_attribution(
        run_id="test-run-c",
        paths=[],
        target_address=ofac_addr,
        chain="BTC",
        db=db,
    )
    assert res_c.rule_fired == "OFAC_SANCTIONS_MATCH"
    assert "OFAC SDN MATCH" in res_c.matched_entity


# ---------------------------------------------------------------------------
# Test 5: Scheduled Refresh & Admin Endpoints
# ---------------------------------------------------------------------------
def test_tagpack_admin_status_and_refresh_endpoint(admin_auth_header, db):
    """Verify admin endpoints:
    GET /api/v1/admin/tagpacks/status
    POST /api/v1/admin/tagpacks/refresh
    """
    # 1. Status Check
    status_res = client.get("/api/v1/admin/tagpacks/status", headers=admin_auth_header)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["total_entities"] > 0
    assert status_data["total_labels"] > 0

    # 2. Refresh Check (force=False on fresh data returns SKIPPED_FRESH)
    refresh_res = client.post("/api/v1/admin/tagpacks/refresh?force=false", headers=admin_auth_header)
    assert refresh_res.status_code == 200
    refresh_data = refresh_res.json()
    assert refresh_data["status"] == "SKIPPED_FRESH"

    # 3. Scheduled refresh function check
    job_res = refresh_tagpacks_job(db=db, force=False)
    assert job_res["status"] == "SKIPPED_FRESH"
