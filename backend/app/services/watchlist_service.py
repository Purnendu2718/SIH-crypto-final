"""Golden Hour Watchlist Service & Webhook Dispatcher.
Monitors watchlisted suspect crypto addresses for outbound transactions toward known VASP off-ramps.
Fires automated alerts (stubbed Telegram webhook behind feature flag).
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models import WatchlistEntry, VASPDirectory, utc_now
from app.services.adapters.base import ChainAdapter
from app.services.adapters.fixture_adapter import FixtureAdapter
from app.services.audit import append_audit_entry

logger = logging.getLogger("sentinel.watchlist")


def dispatch_telegram_alert(
    entry: WatchlistEntry,
    tx_hash: str,
    to_address: str,
    off_ramp_entity: str,
    value: float,
    chain: str,
) -> Dict[str, Any]:
    """Dispatch a Telegram webhook alert or stub the delivery safely based on configuration."""
    alert_payload = {
        "alert_type": "GOLDEN_HOUR_OFFRAMP_DETECTED",
        "case_id": entry.case_id,
        "monitored_address": entry.address,
        "chain": chain,
        "tx_hash": tx_hash,
        "destination_offramp": off_ramp_entity,
        "offramp_address": to_address,
        "amount": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "statutory_action": "Issue Section 94 BNSS emergency account freeze requisition.",
    }

    if settings.ENABLE_TELEGRAM_WEBHOOK and settings.TELEGRAM_BOT_TOKEN:
        try:
            import urllib.request
            import json

            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            msg = (
                f"🚨 *SENTINEL GOLDEN HOUR ALERT*\n"
                f"• Suspect: `{entry.address}`\n"
                f"• Off-Ramp: *{off_ramp_entity}*\n"
                f"• Tx: `{tx_hash}`\n"
                f"• Value: {value} {chain}\n"
                f"• Action: Urgent Sec 94 BNSS Notice required!"
            )
            data = json.dumps({"chat_id": settings.TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(f"Telegram alert dispatched with status {resp.status}")
                return {"dispatched": True, "mode": "LIVE_TELEGRAM", "payload": alert_payload}
        except Exception as ex:
            logger.warning(f"Telegram dispatch failed: {ex}. Falling back to stub.")

    # Stub mode (default for offline-first architecture)
    logger.info(
        f"[STUB TELEGRAM WEBHOOK] Golden Hour Outbound Alert for Case {entry.case_id}: "
        f"Suspect {entry.address} sent {value} {chain} to {off_ramp_entity} ({to_address}). Tx: {tx_hash}"
    )
    return {"dispatched": True, "mode": "STUB_LOGGED", "payload": alert_payload}


def check_watchlist_entry(
    entry: WatchlistEntry,
    db: Session,
    adapter: Optional[ChainAdapter] = None,
) -> Optional[Dict[str, Any]]:
    """Inspect transactions for a watchlisted address and alert on movements to known off-ramps."""
    if adapter is None:
        adapter = FixtureAdapter()

    # Load known VASP hot wallets
    vasp_entries = db.query(VASPDirectory).all()
    hot_wallets_map: Dict[str, str] = {}
    for vasp in vasp_entries:
        for hw in (vasp.hot_wallet_addresses or []):
            hot_wallets_map[hw.lower()] = vasp.entity_name

    txs = adapter.get_transactions(entry.address, entry.chain)

    now = utc_now()
    entry.last_checked_at = now

    for tx in txs:
        # Check outbound transfer from monitored address
        if tx.from_address.lower() == entry.address.lower():
            dest_lower = tx.to_address.lower()
            if dest_lower in hot_wallets_map:
                off_ramp_entity = hot_wallets_map[dest_lower]
                
                # Check if this tx was already alerted
                if entry.last_seen_tx_hash == tx.tx_hash and entry.status == "TRIGGERED":
                    continue

                # Trigger Golden Hour Alert
                alert_info = dispatch_telegram_alert(
                    entry=entry,
                    tx_hash=tx.tx_hash,
                    to_address=tx.to_address,
                    off_ramp_entity=off_ramp_entity,
                    value=tx.value,
                    chain=tx.chain,
                )

                entry.status = "TRIGGERED"
                entry.last_alert_at = now
                entry.last_seen_tx_hash = tx.tx_hash

                append_audit_entry(
                    db=db,
                    officer_id="SYSTEM_WATCHLIST_WORKER",
                    action="GOLDEN_HOUR_WATCHLIST_TRIGGERED",
                    target_id=entry.id,
                )

                return alert_info

    return None


def poll_all_watchlist_entries(
    db: Session,
    adapter: Optional[ChainAdapter] = None,
) -> Dict[str, Any]:
    """Polling worker that scans all active watchlist entries."""
    if adapter is None:
        adapter = FixtureAdapter()

    entries = db.query(WatchlistEntry).filter(WatchlistEntry.status != "PAUSED").all()
    alerts_fired = 0
    alert_details = []

    for entry in entries:
        alert = check_watchlist_entry(entry=entry, db=db, adapter=adapter)
        if alert:
            alerts_fired += 1
            alert_details.append(alert)

    db.commit()

    return {
        "total_checked": len(entries),
        "alerts_fired": alerts_fired,
        "alert_details": alert_details,
    }
