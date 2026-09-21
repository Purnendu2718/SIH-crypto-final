"""UPI-UTR Correlator Service.
Matches victim-submitted UPI Reference / UTR + amount + rough timestamp
against on-chain deposit transactions within configurable time and amount tolerance windows.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.schemas import UTRCandidateMatch, UTRCorrelationResult


def parse_timestamp(ts: Any) -> datetime:
    """Normalize string or datetime to timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    if isinstance(ts, str):
        # Handle ISO format strings like '2026-09-01T10:00:00Z'
        clean_ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"Unsupported timestamp format: {ts}")


class UPICorrelator:
    """Heuristic correlation engine for victim fiat payments and crypto off-ramps."""

    # Default fallback exchange rate if not specified on transaction or parameters
    DEFAULT_ETH_INR_RATE = 250000.0  # Approx 1 ETH = 2,50,000 INR as per demo dataset
    DEFAULT_TRX_INR_RATE = 12.0
    DEFAULT_USDT_INR_RATE = 88.0

    @classmethod
    def get_default_exchange_rate(cls, chain: str) -> float:
        c = (chain or "ETH").upper()
        if "TRON" in c or "TRX" in c:
            return cls.DEFAULT_TRX_INR_RATE
        if "USDT" in c:
            return cls.DEFAULT_USDT_INR_RATE
        return cls.DEFAULT_ETH_INR_RATE

    @classmethod
    def correlate(
        cls,
        victim_utr: str,
        reported_amount_inr: float,
        utr_timestamp: datetime,
        transactions: List[Dict[str, Any]],
        time_tolerance_minutes: float = 120.0,
        amount_tolerance_percent: float = 5.0,
        exchange_rate_inr: Optional[float] = None,
    ) -> UTRCorrelationResult:
        """Evaluate a list of candidate on-chain transactions against victim UTR details.

        Matching heuristic:
        1. Time Delta: |tx_timestamp - utr_timestamp| <= time_tolerance_minutes
        2. Amount Delta: |tx_inr - reported_amount_inr| / reported_amount_inr <= (amount_tolerance_percent / 100)
        3. Composite Correlation Score: 0.5 * time_score + 0.5 * amount_score
        """
        norm_utr_ts = parse_timestamp(utr_timestamp)
        matched_candidates: List[UTRCandidateMatch] = []
        best_candidate: Optional[UTRCandidateMatch] = None
        highest_score = -1.0

        for tx in transactions:
            tx_hash = tx.get("tx_hash", "unknown")
            chain = tx.get("chain", "ETH")
            from_addr = tx.get("from_address", "")
            to_addr = tx.get("to_address", "")
            raw_val = float(tx.get("value", 0.0))

            # Derive INR valuation
            if tx.get("value_inr") is not None:
                tx_inr = float(tx["value_inr"])
            else:
                rate = exchange_rate_inr or cls.get_default_exchange_rate(chain)
                tx_inr = round(raw_val * rate, 2)

            tx_ts_raw = tx.get("timestamp") or tx.get("submitted_at") or norm_utr_ts
            tx_ts = parse_timestamp(tx_ts_raw)

            # 1. Temporal delta
            time_diff_sec = abs((tx_ts - norm_utr_ts).total_seconds())
            time_diff_min = round(time_diff_sec / 60.0, 2)
            time_in_bounds = time_diff_min <= time_tolerance_minutes

            # 2. Amount delta
            amount_diff_inr = round(abs(tx_inr - reported_amount_inr), 2)
            if reported_amount_inr > 0:
                amount_diff_pct = round((amount_diff_inr / reported_amount_inr) * 100.0, 2)
            else:
                amount_diff_pct = 100.0
            amount_in_bounds = amount_diff_pct <= amount_tolerance_percent

            # 3. Composite score
            time_score = max(0.0, 1.0 - (time_diff_min / max(1.0, time_tolerance_minutes)))
            amount_score = max(0.0, 1.0 - (amount_diff_pct / max(0.1, amount_tolerance_percent)))
            composite_score = round(0.5 * time_score + 0.5 * amount_score, 3)

            is_match = time_in_bounds and amount_in_bounds

            if is_match:
                explanation = (
                    f"Candidate tx matches reported UTR '{victim_utr}' within {time_diff_min} mins "
                    f"(limit: {time_tolerance_minutes}m) and {amount_diff_pct}% amount tolerance "
                    f"(limit: {amount_tolerance_percent}%). Value: ₹{tx_inr:,.2f} INR."
                )
            elif not time_in_bounds and not amount_in_bounds:
                explanation = (
                    f"Rejected: Time delta ({time_diff_min}m > {time_tolerance_minutes}m) and "
                    f"amount discrepancy ({amount_diff_pct}% > {amount_tolerance_percent}%) exceed tolerance."
                )
            elif not time_in_bounds:
                explanation = (
                    f"Rejected: Temporal delta of {time_diff_min} minutes exceeds tolerance window "
                    f"of {time_tolerance_minutes} minutes."
                )
            else:
                explanation = (
                    f"Rejected: Amount discrepancy of ₹{amount_diff_inr:,.2f} INR ({amount_diff_pct}%) "
                    f"exceeds tolerance of {amount_tolerance_percent}%."
                )

            candidate = UTRCandidateMatch(
                tx_hash=tx_hash,
                chain=chain,
                from_address=from_addr,
                to_address=to_addr,
                tx_timestamp=tx_ts,
                value=raw_val,
                value_inr=tx_inr,
                time_diff_minutes=time_diff_min,
                amount_diff_inr=amount_diff_inr,
                amount_diff_percent=amount_diff_pct,
                correlation_score=composite_score if is_match else 0.0,
                is_correlated=is_match,
                explanation=explanation,
            )

            if is_match:
                matched_candidates.append(candidate)
                if composite_score > highest_score:
                    highest_score = composite_score
                    best_candidate = candidate

        # Sort matched candidates by correlation score desc
        matched_candidates.sort(key=lambda c: c.correlation_score, reverse=True)

        status = (
            "CORRELATED_MATCH_FOUND" if matched_candidates else "NO_CANDIDATE_WITHIN_TOLERANCE"
        )

        return UTRCorrelationResult(
            victim_utr=victim_utr,
            reported_amount_inr=reported_amount_inr,
            utr_timestamp=norm_utr_ts,
            time_tolerance_minutes=time_tolerance_minutes,
            amount_tolerance_percent=amount_tolerance_percent,
            total_candidates_evaluated=len(transactions),
            matched_candidates=matched_candidates,
            best_candidate=best_candidate,
            correlation_status=status,
        )
