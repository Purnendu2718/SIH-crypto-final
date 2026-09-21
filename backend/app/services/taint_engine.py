"""FIFO Contamination Accounting Taint Engine.
Calculates the exact percentage of a wallet's balance and transaction flow
attributable to the victim-reported crime proceeds.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from app.models import TracePath


class HopTaintRecord:
    def __init__(
        self,
        hop_index: int,
        from_address: str,
        to_address: str,
        transferred_value: float,
        tainted_value: float,
        taint_percentage: float,
    ):
        self.hop_index = hop_index
        self.from_address = from_address
        self.to_address = to_address
        self.transferred_value = transferred_value
        self.tainted_value = tainted_value
        self.taint_percentage = taint_percentage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hop_index": self.hop_index,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "transferred_value": round(self.transferred_value, 6),
            "tainted_value": round(self.tainted_value, 6),
            "taint_percentage": round(self.taint_percentage, 2),
        }


class TaintResult:
    def __init__(
        self,
        initial_stolen_amount: float,
        final_taint_percentage: float,
        final_tainted_value: float,
        hop_progression: List[HopTaintRecord],
    ):
        self.initial_stolen_amount = initial_stolen_amount
        self.final_taint_percentage = final_taint_percentage
        self.final_tainted_value = final_tainted_value
        self.hop_progression = hop_progression

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_stolen_amount": round(self.initial_stolen_amount, 6),
            "final_taint_percentage": round(self.final_taint_percentage, 2),
            "final_tainted_value": round(self.final_tainted_value, 6),
            "clean_value": round(max(0.0, (self.hop_progression[-1].transferred_value - self.final_tainted_value) if self.hop_progression else 0.0), 6),
            "hop_progression": [h.to_dict() for h in self.hop_progression],
        }


class TaintEngine:
    """FIFO (First-In-First-Out) contamination accounting engine."""

    def compute_fifo_taint(
        self,
        paths: List[TracePath],
        stolen_principal: Optional[float] = None,
    ) -> TaintResult:
        """Compute FIFO contamination ratio hop-by-hop along the trace path."""
        if not paths:
            return TaintResult(
                initial_stolen_amount=0.0,
                final_taint_percentage=0.0,
                final_tainted_value=0.0,
                hop_progression=[],
            )

        # Establish starting stolen principal (default to initial hop value if not provided)
        first_hop_val = float(paths[0].value) if paths[0].value else 0.0
        initial_stolen = stolen_principal if (stolen_principal is not None and stolen_principal > 0) else first_hop_val

        incoming_tainted = initial_stolen
        hop_records: List[HopTaintRecord] = []

        for p in paths:
            hop_val = float(p.value) if p.value else 0.0

            if hop_val <= 0:
                taint_pct = 0.0
                tainted_amount = 0.0
            elif incoming_tainted >= hop_val:
                # Under FIFO, all transferred funds are tainted (up to incoming tainted amount)
                tainted_amount = hop_val
                taint_pct = 100.0
                incoming_tainted = hop_val
            else:
                # Transferred amount exceeds incoming tainted funds (dilution with clean funds)
                tainted_amount = incoming_tainted
                taint_pct = (tainted_amount / hop_val) * 100.0
                incoming_tainted = tainted_amount

            hop_records.append(
                HopTaintRecord(
                    hop_index=p.hop_index,
                    from_address=p.from_addr,
                    to_address=p.to_addr,
                    transferred_value=hop_val,
                    tainted_value=tainted_amount,
                    taint_percentage=taint_pct,
                )
            )

        final_record = hop_records[-1] if hop_records else None
        final_pct = final_record.taint_percentage if final_record else 0.0
        final_val = final_record.tainted_value if final_record else 0.0

        return TaintResult(
            initial_stolen_amount=initial_stolen,
            final_taint_percentage=final_pct,
            final_tainted_value=final_val,
            hop_progression=hop_records,
        )
