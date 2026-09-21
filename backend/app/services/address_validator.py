"""
CryptoTrace Sentinel - multi-chain address / identifier validator (v3)

Pure Python 3.9+, standard library only, no network access.

Design rules
  1. Verify the checksum wherever a chain defines one: Base58Check (BTC family,
     TRON, Zcash), XRPL (Base58Check with the Ripple alphabet), Bech32 / Bech32m
     (SegWit, Taproot, Cosmos family, Cardano), CashAddr (BCH), EIP-55 (EVM),
     Monero, SS58 (Polkadot / Kusama / Substrate), Stellar strkey.
  2. Where a chain has NO checksum (Solana, all-lowercase EVM addresses) say so:
     the result is certainty="format_only", never "verified".
  3. Many strings are legitimately valid on several chains (every EVM chain shares
     one address format; legacy "3..." can be BTC, BCH or LTC). All candidates are
     returned; nothing is guessed. On-chain lookup is what disambiguates.

Ethereum and Monero use the ORIGINAL Keccak-256 padding, which differs from the
NIST SHA3-256 in hashlib. Using hashlib.sha3_256 for EIP-55 silently rejects
valid checksummed addresses, so Keccak is implemented below.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

MAX_INPUT_LEN = 200  # longest legit identifier we handle is ~110 chars

# ---------------------------------------------------------------------------
# Keccak-256 (Ethereum / Monero flavour)
# ---------------------------------------------------------------------------

_M64 = (1 << 64) - 1
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROTC = [1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44]
_PILN = [10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1]


def _rol64(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _M64


def _keccak_f(a: List[int]) -> None:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        for x in range(5):
            d = c[(x + 4) % 5] ^ _rol64(c[(x + 1) % 5], 1)
            for y in range(0, 25, 5):
                a[y + x] ^= d
        t = a[1]
        for i in range(24):
            j = _PILN[i]
            a[j], t = _rol64(t, _ROTC[i]), a[j]
        for y in range(0, 25, 5):
            row = a[y:y + 5]
            for x in range(5):
                a[y + x] = row[x] ^ ((~row[(x + 1) % 5]) & row[(x + 2) % 5])
        a[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data)
    msg.append(0x01)
    while len(msg) % rate:
        msg.append(0)
    msg[-1] |= 0x80
    st = [0] * 25
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(st)
    return b"".join(st[i].to_bytes(8, "little") for i in range(4))


# ---------------------------------------------------------------------------
# Base58 / Base58Check
# ---------------------------------------------------------------------------

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
XRP_B58 = "rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz"


def b58decode(s: str, alphabet: str = B58) -> Optional[bytes]:
    n = 0
    for ch in s:
        i = alphabet.find(ch)
        if i < 0:
            return None
        n = n * 58 + i
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip(alphabet[0]))
    return b"\x00" * pad + body


def b58encode(b: bytes, alphabet: str = B58) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = alphabet[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return alphabet[0] * pad + out


def _dsha(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def b58check_decode(s: str, alphabet: str = B58) -> Optional[bytes]:
    """Return payload (version byte(s) + data) if the 4-byte checksum matches."""
    raw = b58decode(s, alphabet)
    if raw is None or len(raw) < 5:
        return None
    payload, chk = raw[:-4], raw[-4:]
    return payload if _dsha(payload)[:4] == chk else None


def b58check_encode(payload: bytes, alphabet: str = B58) -> str:
    return b58encode(payload + _dsha(payload)[:4], alphabet)


# ---------------------------------------------------------------------------
# Bech32 / Bech32m (BIP-173 / BIP-350) and CashAddr
# ---------------------------------------------------------------------------

_B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M_CONST = 0x2BC830A3


def _bech32_polymod(values: List[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    return chk


def _hrp_expand(hrp: str) -> List[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_decode(s: str, limit: Optional[int] = 90) -> Optional[Tuple[str, List[int], str]]:
    """Return (hrp, 5-bit data without checksum, 'bech32'|'bech32m') or None."""
    if any(ord(c) < 33 or ord(c) > 126 for c in s):
        return None
    if s != s.lower() and s != s.upper():
        return None
    s = s.lower()
    pos = s.rfind("1")
    if pos < 1 or pos + 7 > len(s) or (limit is not None and len(s) > limit):
        return None
    if any(c not in _B32 for c in s[pos + 1:]):
        return None
    hrp = s[:pos]
    data = [_B32.find(c) for c in s[pos + 1:]]
    pm = _bech32_polymod(_hrp_expand(hrp) + data)
    if pm == 1:
        return hrp, data[:-6], "bech32"
    if pm == _BECH32M_CONST:
        return hrp, data[:-6], "bech32m"
    return None


def bech32_encode(hrp: str, data5: List[int], spec: str = "bech32") -> str:
    const = 1 if spec == "bech32" else _BECH32M_CONST
    pm = _bech32_polymod(_hrp_expand(hrp) + data5 + [0] * 6) ^ const
    chk = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_B32[d] for d in data5 + chk)


def convertbits(data, frombits: int, tobits: int, pad: bool = True) -> Optional[List[int]]:
    acc = bits = 0
    ret: List[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for v in data:
        if v < 0 or (v >> frombits):
            return None
        acc = ((acc << frombits) | v) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def _segwit_decode(hrp_expected: str, hrp: str, data: List[int], spec: str) -> Optional[Tuple[int, bytes]]:
    if hrp != hrp_expected or not data or data[0] > 16:
        return None
    prog = convertbits(data[1:], 5, 8, False)
    if prog is None or not (2 <= len(prog) <= 40):
        return None
    ver = data[0]
    if ver == 0 and len(prog) not in (20, 32):
        return None
    if (ver == 0) != (spec == "bech32"):  # v0 => bech32, v1+ => bech32m
        return None
    return ver, bytes(prog)


def _cashaddr_polymod(values: List[int]) -> int:
    gen = [0x98F2BC8E61, 0x79B76D99E2, 0xF33E5FB3C4, 0xAE2EABE2A8, 0x1E4F43E470]
    c = 1
    for d in values:
        c0 = c >> 35
        c = ((c & 0x07FFFFFFFF) << 5) ^ d
        for i in range(5):
            if (c0 >> i) & 1:
                c ^= gen[i]
    return c ^ 1


def _cashaddr_decode(s: str) -> Optional[Tuple[str, str, bytes]]:
    if s != s.lower() and s != s.upper():
        return None
    s = s.lower()
    prefix, payload = s.split(":", 1) if ":" in s else ("bitcoincash", s)
    if prefix not in ("bitcoincash", "bchtest", "bchreg") or not payload:
        return None
    if any(c not in _B32 for c in payload):
        return None
    vals = [_B32.find(c) for c in payload]
    if _cashaddr_polymod([ord(c) & 31 for c in prefix] + [0] + vals) != 0:
        return None
    data = convertbits(vals[:-8], 5, 8, False)
    if not data or len(data) != 21 or (data[0] & 7) != 0:  # only 160-bit hashes
        return None
    typ = {0: "p2pkh", 1: "p2sh"}.get(data[0] >> 3)
    if typ is None:
        return None
    return prefix, typ, bytes(data[1:])


# ---------------------------------------------------------------------------
# EIP-55 (EVM)
# ---------------------------------------------------------------------------

def to_checksum_address(addr: str) -> str:
    body = addr[2:] if addr[:2].lower() == "0x" else addr
    body = body.lower()
    h = keccak256(body.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(body))


EVM_CHAINS = [
    "ethereum", "polygon", "arbitrum", "optimism", "base", "bnb_smart_chain",
    "avalanche_c", "linea", "zksync_era", "scroll", "gnosis", "celo", "mantle", "fantom",
]


# ---------------------------------------------------------------------------
# Monero (block-wise Base58 + Keccak checksum)
# ---------------------------------------------------------------------------

_XMR_BLOCK_BYTES = {2: 1, 3: 2, 5: 3, 6: 4, 7: 5, 9: 6, 10: 7, 11: 8}


def _xmr_b58_decode(s: str) -> Optional[bytes]:
    full, rem = divmod(len(s), 11)
    if rem and rem not in _XMR_BLOCK_BYTES:
        return None
    chunks = [s[i * 11:(i + 1) * 11] for i in range(full)] + ([s[full * 11:]] if rem else [])
    out = bytearray()
    for ch in chunks:
        size = 8 if len(ch) == 11 else _XMR_BLOCK_BYTES[len(ch)]
        n = 0
        for c in ch:
            i = B58.find(c)
            if i < 0:
                return None
            n = n * 58 + i
        if n >> (8 * size):
            return None
        out += n.to_bytes(size, "big")
    return bytes(out)


_XMR_PREFIX = {
    18: ("standard", "mainnet"), 19: ("integrated", "mainnet"), 42: ("subaddress", "mainnet"),
    53: ("standard", "testnet"), 54: ("integrated", "testnet"), 63: ("subaddress", "testnet"),
    24: ("standard", "stagenet"), 25: ("integrated", "stagenet"), 36: ("subaddress", "stagenet"),
}


# ---------------------------------------------------------------------------
# Stellar strkey, SS58
# ---------------------------------------------------------------------------

def _crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _stellar_ok(s: str) -> bool:
    if not re.fullmatch(r"G[A-Z2-7]{55}", s):
        return False
    raw = base64.b32decode(s)
    return raw[0] == 6 << 3 and _crc16_xmodem(raw[:-2]) == int.from_bytes(raw[-2:], "little")


_SS58_NAMES = {0: "polkadot", 2: "kusama", 42: "substrate_generic"}


def _ss58_decode(s: str) -> Optional[int]:
    """Return the network prefix if `s` is a valid single-byte-prefix SS58 address."""
    raw = b58decode(s)
    if raw is None or len(raw) != 35 or raw[0] >= 64:
        return None
    chk = hashlib.blake2b(b"SS58PRE" + raw[:-2], digest_size=64).digest()[:2]
    return raw[0] if chk == raw[-2:] else None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    chain: str
    address_type: str
    network: str = "mainnet"
    checksum_verified: bool = True
    note: Optional[str] = None


@dataclass
class ValidationResult:
    input: str
    normalized: str = ""
    is_valid: bool = False
    kind: str = "unknown"      # address | transaction_hash | ens_name | unknown
    certainty: str = "none"    # verified | format_only | none
    candidates: List[Candidate] = field(default_factory=list)
    related_chains: List[str] = field(default_factory=list)
    error: Optional[str] = None
    hint: Optional[str] = None

    @property
    def primary(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["primary"] = asdict(self.primary) if self.primary else None
        return d


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00a0"), None)
_URI = re.compile(r"^(bitcoin|litecoin|ethereum|dogecoin|monero|tron|solana|ripple|stellar|dash|zcash|polkadot):([^?@/#]+)", re.I)


def normalize(q: str) -> str:
    s = q.translate(_ZERO_WIDTH).strip()
    s = s.strip("\"'`<>()[]{}").rstrip(".,;:").strip()
    m = _URI.match(s)
    if m:
        s = m.group(2)
    return s


# ---------------------------------------------------------------------------
# Family detectors. Each returns a list of Candidates (empty if no match).
# ---------------------------------------------------------------------------

_LEGACY_NOTE = "Legacy Base58 format is shared by Bitcoin forks; on-chain lookup confirms the chain."

_B58_VERSIONS = {
    0x00: [("bitcoin", "p2pkh", "mainnet", None), ("bitcoin_cash", "p2pkh_legacy", "mainnet", _LEGACY_NOTE)],
    0x05: [("bitcoin", "p2sh", "mainnet", None), ("bitcoin_cash", "p2sh_legacy", "mainnet", _LEGACY_NOTE),
           ("litecoin", "p2sh_legacy", "mainnet", _LEGACY_NOTE)],
    0x30: [("litecoin", "p2pkh", "mainnet", None)],
    0x32: [("litecoin", "p2sh", "mainnet", None)],
    0x1E: [("dogecoin", "p2pkh", "mainnet", None)],
    0x16: [("dogecoin", "p2sh", "mainnet", None)],
    0x4C: [("dash", "p2pkh", "mainnet", None)],
    0x10: [("dash", "p2sh", "mainnet", None)],
    0x6F: [("bitcoin", "p2pkh", "testnet", None), ("litecoin", "p2pkh", "testnet", None)],
    0xC4: [("bitcoin", "p2sh", "testnet", None), ("litecoin", "p2sh", "testnet", None)],
}
_ZCASH = {b"\x1c\xb8": "p2pkh", b"\x1c\xbd": "p2sh"}

_SEGWIT_HRP = {
    "bc": ("bitcoin", "mainnet"), "tb": ("bitcoin", "testnet"), "bcrt": ("bitcoin", "regtest"),
    "ltc": ("litecoin", "mainnet"), "tltc": ("litecoin", "testnet"),
}
_COSMOS_HRP = {
    "cosmos": "cosmos", "osmo": "osmosis", "juno": "juno", "sei": "sei", "inj": "injective",
    "celestia": "celestia", "akash": "akash", "kava": "kava", "terra": "terra",
    "secret": "secret", "stars": "stargaze",
}
_CARDANO_HRP = ("addr", "addr_test", "stake", "stake_test")


def _try_evm(s: str, res: ValidationResult) -> List[Candidate]:
    # EIP-55 carries only ~1 bit of checksum per letter (a-f), so a mixed-case address that
    # happens to contain very few letters is only weakly verified. That is a property of the
    # standard, not of this code. All-lowercase / all-uppercase input is reported as format_only.
    m = re.fullmatch(r"(?:0[xX])?([0-9a-fA-F]{40})", s)
    if not m:
        return []
    body = m.group(1)
    has_prefix = s[:2].lower() == "0x"
    mixed = body != body.lower() and body != body.upper()
    checksummed = to_checksum_address(body)
    if mixed and checksummed[2:] != body:
        res.error = "Mixed-case EVM address fails the EIP-55 checksum (typo, or case was altered)."
        res.hint = "If you know the address is right, paste it all-lowercase to skip the checksum (certainty becomes format_only)."
        return []
    res.normalized = checksummed
    res.related_chains = list(EVM_CHAINS)
    note = "Same address exists on every EVM chain; query each chain to see where it is active."
    if not has_prefix:
        note += " Input had no 0x prefix."
    return [Candidate("ethereum", "eoa_or_contract", "mainnet", checksum_verified=mixed, note=note)]


def _try_base58check(s: str, res: ValidationResult) -> List[Candidate]:
    payload = b58check_decode(s)
    if payload is None:
        return []
    if len(payload) == 21 and payload[0] == 0x41:
        return [Candidate("tron", "base58check", "mainnet")]
    if len(payload) == 21 and payload[0] in _B58_VERSIONS:
        return [Candidate(c, t, n, True, note) for c, t, n, note in _B58_VERSIONS[payload[0]]]
    if len(payload) == 22 and payload[:2] in _ZCASH:
        return [Candidate("zcash", _ZCASH[payload[:2]] + "_transparent", "mainnet")]
    res.error = f"Valid Base58Check, but version byte 0x{payload[0]:02x} (payload {len(payload)} bytes) is not a supported chain."
    return []


def _try_xrp(s: str) -> List[Candidate]:
    if s[:1] != "r" or not (25 <= len(s) <= 35):
        return []
    payload = b58check_decode(s, XRP_B58)
    if payload is not None and len(payload) == 21 and payload[0] == 0x00:
        return [Candidate("xrp_ledger", "account", "mainnet")]
    return []


def _try_ss58(s: str) -> List[Candidate]:
    if not (46 <= len(s) <= 48):
        return []
    prefix = _ss58_decode(s)
    if prefix is None:
        return []
    return [Candidate(_SS58_NAMES.get(prefix, f"substrate_ss58_prefix_{prefix}"), "ss58", "mainnet")]


def _try_stellar(s: str) -> List[Candidate]:
    return [Candidate("stellar", "ed25519_account", "mainnet")] if _stellar_ok(s) else []


def _try_bech32_family(s: str, res: ValidationResult) -> List[Candidate]:
    dec = bech32_decode(s, limit=None)
    if dec is None:
        return []
    hrp, data, spec = dec
    res.normalized = s.lower()
    if hrp in _SEGWIT_HRP and len(s) <= 90:
        chain, net = _SEGWIT_HRP[hrp]
        sw = _segwit_decode(hrp, hrp, data, spec)
        if sw is None:
            res.error = f"Valid {spec} checksum but not a valid SegWit program for '{hrp}'."
            return []
        ver, prog = sw
        typ = {(0, 20): "p2wpkh", (0, 32): "p2wsh", (1, 32): "p2tr"}.get((ver, len(prog)), f"witness_v{ver}")
        return [Candidate(chain, typ, net)]
    if hrp in _COSMOS_HRP and spec == "bech32" and len(s) <= 90:
        prog = convertbits(data, 5, 8, False)
        if prog is not None and len(prog) in (20, 32):
            return [Candidate(_COSMOS_HRP[hrp], "bech32_account", "mainnet")]
        res.error = f"Valid Bech32 checksum but '{hrp}' payload has an unexpected length."
        return []
    if hrp in _CARDANO_HRP and spec == "bech32":
        net = "testnet" if hrp.endswith("_test") else "mainnet"
        return [Candidate("cardano", "shelley_stake" if hrp.startswith("stake") else "shelley", net)]
    if len(s) <= 90:
        return [Candidate(f"bech32:{hrp}", "unknown_hrp", "unknown", True,
                          "Checksum valid but the prefix is not one this validator maps to a chain.")]
    return []


def _try_cashaddr(s: str) -> List[Candidate]:
    if not re.fullmatch(r"(?i)(?:(?:bitcoincash|bchtest|bchreg):)?[qp][a-z0-9]{41}", s):
        return []
    dec = _cashaddr_decode(s)
    if dec is None:
        return []
    prefix, typ, _ = dec
    return [Candidate("bitcoin_cash", "cashaddr_" + typ, "mainnet" if prefix == "bitcoincash" else "testnet")]


def _try_monero(s: str) -> List[Candidate]:
    if len(s) not in (95, 106) or s[0] not in "4589ABCDEFGHJKLMNPQRSTUVWXYZ":
        return []
    raw = _xmr_b58_decode(s)
    if raw is None or len(raw) not in (69, 77):
        return []
    if keccak256(raw[:-4])[:4] != raw[-4:]:
        return []
    kind_net = _XMR_PREFIX.get(raw[0])
    if kind_net is None or (kind_net[0] == "integrated") != (len(raw) == 77):
        return []
    return [Candidate("monero", kind_net[0], kind_net[1], True,
                      "Privacy chain: balance and history cannot be derived from the address alone.")]


def _try_solana(s: str) -> List[Candidate]:
    if not (32 <= len(s) <= 44):
        return []
    raw = b58decode(s)
    if raw is not None and len(raw) == 32:
        return [Candidate("solana", "ed25519_pubkey", "mainnet", False,
                          "Solana addresses have no checksum: any 32-byte Base58 string is structurally valid.")]
    return []


def _try_tx_hash(s: str, res: ValidationResult) -> bool:
    if re.fullmatch(r"0[xX][0-9a-fA-F]{64}", s):
        res.kind, res.normalized = "transaction_hash", s.lower()
        res.candidates = [Candidate(c, "tx_hash", "mainnet", False,
                                    "0x + 64 hex is an EVM tx hash (or a Sui/Aptos address); look it up per chain.")
                          for c in EVM_CHAINS]
        return True
    if re.fullmatch(r"[0-9a-fA-F]{64}", s):
        res.kind, res.normalized = "transaction_hash", s.lower()
        res.candidates = [Candidate(c, "tx_hash", "mainnet", False,
                                    "64-hex hash has no checksum; probe chains via lookup.")
                          for c in ("bitcoin", "litecoin", "dogecoin", "bitcoin_cash", "dash", "zcash",
                                    "tron", "xrp_ledger", "stellar", "monero")]
        return True
    if 80 <= len(s) <= 90:
        raw = b58decode(s)
        if raw is not None and len(raw) == 64:
            res.kind, res.normalized = "transaction_hash", s
            res.candidates = [Candidate("solana", "tx_signature", "mainnet", False,
                                        "Solana transaction signature (64 bytes, no checksum).")]
            return True
    return False


# ---------------------------------------------------------------------------
# Diagnostics for inputs that match nothing
# ---------------------------------------------------------------------------

def _diagnose(s: str, res: ValidationResult) -> None:
    if res.error:
        return
    if re.search(r"\s", s):
        res.error = "Input contains whitespace inside the identifier."
        res.hint = "Remove spaces or line breaks that were added when copying."
    elif s.lower().endswith(".eth"):
        res.kind = "ens_name"
        res.error = "This is an ENS name, not an address."
        res.hint = "Resolve it to a 0x address (needs a network lookup), then search that address."
    elif re.fullmatch(r"0[xX][0-9a-fA-F]*", s):
        res.error = f"EVM addresses are 0x + 40 hex characters; this has {len(s) - 2} hex characters."
    elif re.fullmatch(r"0[xX].*", s):
        res.error = "Starts with 0x but contains non-hex characters."
    elif s[:1] in "13LMDX79Tt" and 25 <= len(s) <= 36:
        bad = sorted({c for c in s if c not in B58})
        if bad:
            res.error = f"Contains characters that are not valid in Base58: {' '.join(bad)} (0, O, I and l are excluded)."
            res.hint = "Look-alike characters are the most common copy/typing error."
        else:
            res.error = "Right shape for a Base58Check address but the checksum fails: typo, truncation or a fabricated address."
    elif re.match(r"(?i)^(bc1|tb1|ltc1|cosmos1|osmo1|addr1)", s):
        res.error = "Bech32 checksum or structure is invalid: typo, truncation or wrong case mix."
    else:
        res.error = "Unrecognised format."
        res.hint = ("Supported: BTC/LTC/DOGE/DASH/ZEC/BCH, EVM (0x), TRON, XRP, Stellar, Polkadot/Kusama, "
                    "Solana, Cosmos family, Cardano (Shelley), Monero, and 64-hex transaction hashes.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(query: str) -> ValidationResult:
    """Classify `query` as an address / transaction hash and verify it."""
    res = ValidationResult(input=query if isinstance(query, str) else "")
    if not isinstance(query, str) or not query.strip():
        res.error = "Empty input."
        return res
    s = normalize(query)
    res.normalized = s
    if not s:
        res.error = "Empty input."
        return res
    if len(s) > MAX_INPUT_LEN:
        res.error = f"Input too long ({len(s)} chars); no supported identifier exceeds {MAX_INPUT_LEN}."
        return res

    if _try_tx_hash(s, res):
        res.is_valid, res.certainty = True, "format_only"
        return res

    cands: List[Candidate] = []
    cands += _try_evm(s, res)
    if not cands:
        cands += _try_base58check(s, res)
        cands += _try_xrp(s)
        cands += _try_ss58(s)
        cands += _try_stellar(s)
        cands += _try_bech32_family(s, res)
        cands += _try_cashaddr(s)
        cands += _try_monero(s)
        if not cands:
            cands += _try_solana(s)

    if cands:
        res.is_valid, res.kind, res.candidates, res.error = True, "address", cands, None
        res.certainty = "verified" if cands[0].checksum_verified else "format_only"
        return res

    _diagnose(s, res)
    return res


def validate_address(address: str) -> ValidationResult:  # backwards-compatible alias
    return validate(address)


def validate_and_detect_chain(address: str) -> Tuple[bool, str, str]:
    """Backwards-compatible helper mapping validate() to (is_valid, chain, detail)."""
    res = validate(address)
    if res.is_valid and res.kind == "address" and res.candidates:
        cand = res.candidates[0]
        chain_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "tron": "TRON",
            "solana": "SOL",
            "litecoin": "LTC",
            "dogecoin": "DOGE",
            "bitcoin_cash": "BCH",
            "xrp_ledger": "XRP",
            "stellar": "XLM",
            "cardano": "ADA",
            "monero": "XMR",
        }
        det_chain = chain_map.get(cand.chain, cand.chain.upper())
        detail = f"{cand.chain.upper()} {cand.address_type.upper()}"
        return (True, det_chain, detail)
    return (False, "UNRECOGNIZED_ADDRESS_FORMAT", res.error or "Invalid address format")


def is_valid_evm_address(addr: str) -> bool:
    v = validate(addr)
    return v.is_valid and any(c.chain == "ethereum" for c in v.candidates)


def validate_base58check(addr: str) -> Tuple[bool, Optional[int], Optional[bytes]]:
    payload = b58check_decode(addr)
    if payload is None or len(payload) == 0:
        return (False, None, None)
    return (True, payload[0], payload[1:])


def is_valid_bech32_btc(addr: str) -> bool:
    v = validate(addr)
    return v.is_valid and any(
        c.chain == "bitcoin" and any(t in c.address_type for t in ("p2wpkh", "p2wsh", "p2tr", "segwit"))
        for c in v.candidates
    )




if __name__ == "__main__":
    import json
    import sys
    for arg in sys.argv[1:] or ["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"]:
        print(json.dumps(validate(arg).to_dict(), indent=2))
