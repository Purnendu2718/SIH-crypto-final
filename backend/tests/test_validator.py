"""
Tests for address_validator.py.  Run:  python -m unittest test_validator -v

Vector provenance
  * REAL vectors are published examples (BIP-173/350, EIP-55, Bitcoin genesis block,
    Monero/Polkadot/Stellar/CashAddr/CIP-19 docs, well-known contracts).  Every one of
    them must pass an actual checksum, so a mis-remembered address cannot slip in.
  * SYNTHETIC vectors are built with the module's own encoders to exercise version
    bytes / prefixes for which no memorised real address is at hand.
"""

import os
import sys
import time
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_services = os.path.abspath(os.path.join(_here, "..", "app", "services"))
if _services not in sys.path:
    sys.path.insert(0, _services)

from address_validator import (
    B58, _B32, b58check_encode, bech32_encode, convertbits, keccak256, to_checksum_address, validate,
)

# address -> (chain, address_type, network, certainty)
REAL = {
    # Bitcoin ---------------------------------------------------------------
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": ("bitcoin", "p2pkh", "mainnet", "verified"),   # genesis block coinbase
    "12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S": ("bitcoin", "p2pkh", "mainnet", "verified"),   # block-170 recipient
    "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2": ("bitcoin", "p2pkh", "mainnet", "verified"),
    "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy": ("bitcoin", "p2sh", "mainnet", "verified"),
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4": ("bitcoin", "p2wpkh", "mainnet", "verified"),           # BIP-173
    "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3": ("bitcoin", "p2wsh", "mainnet", "verified"),  # BIP-173
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0": ("bitcoin", "p2tr", "mainnet", "verified"),  # BIP-350
    "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx": ("bitcoin", "p2wpkh", "testnet", "verified"),
    "mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn": ("bitcoin", "p2pkh", "testnet", "verified"),
    # Other UTXO chains ------------------------------------------------------
    "ltc1qw508d6qejxtdg4y5r3zarvary0c5xw7kgmn4n9": ("litecoin", "p2wpkh", "mainnet", "verified"),
    "DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L": ("dogecoin", "p2pkh", "mainnet", "verified"),
    "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a": ("bitcoin_cash", "cashaddr_p2pkh", "mainnet", "verified"),
    # EVM (EIP-55 spec vectors) ---------------------------------------------
    "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed": ("ethereum", "eoa_or_contract", "mainnet", "verified"),
    "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359": ("ethereum", "eoa_or_contract", "mainnet", "verified"),
    "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB": ("ethereum", "eoa_or_contract", "mainnet", "verified"),
    "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb": ("ethereum", "eoa_or_contract", "mainnet", "verified"),
    # Others ----------------------------------------------------------------
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": ("tron", "base58check", "mainnet", "verified"),     # USDT-TRC20 contract
    "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh": ("xrp_ledger", "account", "mainnet", "verified"),
    "GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7": ("stellar", "ed25519_account", "mainnet", "verified"),
    "15oF4uVJwmo4TdGW7VfQxNLavjCXviqxT9S1MgbjMNHr6Sp5": ("polkadot", "ss58", "mainnet", "verified"),
    "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY": ("substrate_generic", "ss58", "mainnet", "verified"),
    "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRj5UzqtReoS44qo9mtmXCqY45DJ852K5Jv2684Rge":
        ("monero", "standard", "mainnet", "verified"),
    "addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgse35a3x":
        ("cardano", "shelley", "mainnet", "verified"),
}

# No checksum exists for these, so they can only ever be "format_only".
FORMAT_ONLY = {
    "11111111111111111111111111111111": "solana",                       # System Program
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "solana",            # SPL Token Program
}


def _mutations(addr: str):
    """Yield single-character corruptions that must be rejected."""
    body_start = addr.find(":") + 1
    if addr.lower().startswith(("bc1", "tb1", "ltc1", "addr1", "cosmos1")) or addr.startswith("bitcoincash:"):
        alphabet = _B32
    else:
        alphabet = B58
    for i in range(body_start + 3, len(addr), max(1, len(addr) // 20)):
        for c in alphabet[:5]:
            if c != addr[i]:
                yield addr[:i] + c + addr[i + 1:]


class TestKeccak(unittest.TestCase):
    def test_known_digests(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_rate_boundaries(self):
        for n in (135, 136, 137, 272):
            self.assertEqual(len(keccak256(b"a" * n)), 32)


class TestRealVectors(unittest.TestCase):
    def test_all_real_vectors(self):
        for addr, (chain, typ, net, cert) in REAL.items():
            with self.subTest(addr=addr):
                r = validate(addr)
                self.assertTrue(r.is_valid, r.error)
                self.assertEqual(r.kind, "address")
                p = r.primary
                self.assertEqual((p.chain, p.address_type, p.network, r.certainty), (chain, typ, net, cert))

    def test_satoshi_genesis_address(self):
        r = validate("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        self.assertTrue(r.is_valid)
        self.assertEqual(r.primary.chain, "bitcoin")
        self.assertEqual(r.certainty, "verified")

    def test_single_char_corruption_always_rejected(self):
        for addr in REAL:
            for bad in _mutations(addr):
                with self.subTest(addr=addr, bad=bad):
                    self.assertFalse(validate(bad).is_valid, f"corrupted address accepted: {bad}")


class TestFormatOnly(unittest.TestCase):
    def test_solana_is_never_marked_verified(self):
        for addr, chain in FORMAT_ONLY.items():
            r = validate(addr)
            self.assertTrue(r.is_valid)
            self.assertEqual(r.primary.chain, chain)
            self.assertEqual(r.certainty, "format_only")
            self.assertFalse(r.primary.checksum_verified)

    def test_solana_typo_cannot_be_detected(self):
        # Documenting the limitation: no checksum, so a typo is still a well-formed key.
        r = validate("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DB")
        self.assertTrue(r.is_valid)
        self.assertEqual(r.certainty, "format_only")


class TestEVM(unittest.TestCase):
    OFFICIAL = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"

    def test_lower_and_upper_are_format_only(self):
        for form in (self.OFFICIAL.lower(), "0x" + self.OFFICIAL[2:].upper()):
            r = validate(form)
            self.assertTrue(r.is_valid)
            self.assertEqual(r.certainty, "format_only")
            self.assertEqual(r.normalized, self.OFFICIAL)

    def test_bad_mixed_case_rejected(self):
        # Real address with one letter's case flipped (the earlier build's "example ETH address" was of this kind).
        bad = "0x5aAeb6053f3E8C9c9aaB75c6b375c92d52A955F0"
        r = validate(bad)
        self.assertFalse(r.is_valid)
        self.assertIn("EIP-55", r.error)
        flipped = self.OFFICIAL[:3] + self.OFFICIAL[3].swapcase() + self.OFFICIAL[4:]
        self.assertFalse(validate(flipped).is_valid)

    def test_every_evm_chain_listed(self):
        r = validate(self.OFFICIAL)
        self.assertIn("polygon", r.related_chains)
        self.assertIn("arbitrum", r.related_chains)

    def test_no_prefix_and_wrong_length(self):
        self.assertTrue(validate(self.OFFICIAL[2:].lower()).is_valid)
        self.assertFalse(validate(self.OFFICIAL[:-1]).is_valid)
        self.assertIn("39", validate(self.OFFICIAL[:-1]).error)

    def test_checksum_helper_roundtrip(self):
        self.assertEqual(to_checksum_address(self.OFFICIAL.lower()), self.OFFICIAL)


class TestSyntheticVersions(unittest.TestCase):
    H = bytes(range(20))

    def _chain(self, payload):
        r = validate(b58check_encode(payload))
        self.assertTrue(r.is_valid)
        return r.primary.chain, r.primary.address_type

    def test_version_bytes(self):
        self.assertEqual(self._chain(b"\x30" + self.H), ("litecoin", "p2pkh"))
        self.assertEqual(self._chain(b"\x32" + self.H), ("litecoin", "p2sh"))
        self.assertEqual(self._chain(b"\x1e" + self.H), ("dogecoin", "p2pkh"))
        self.assertEqual(self._chain(b"\x16" + self.H), ("dogecoin", "p2sh"))
        self.assertEqual(self._chain(b"\x4c" + self.H), ("dash", "p2pkh"))
        self.assertEqual(self._chain(b"\x10" + self.H), ("dash", "p2sh"))
        self.assertEqual(self._chain(b"\x1c\xb8" + self.H), ("zcash", "p2pkh_transparent"))
        self.assertEqual(self._chain(b"\x1c\xbd" + self.H), ("zcash", "p2sh_transparent"))
        self.assertEqual(self._chain(b"\x41" + self.H), ("tron", "base58check"))

    def test_prefix_letters(self):
        self.assertTrue(b58check_encode(b"\x30" + self.H).startswith("L"))
        self.assertTrue(b58check_encode(b"\x1e" + self.H).startswith("D"))
        self.assertTrue(b58check_encode(b"\x4c" + self.H).startswith("X"))
        self.assertTrue(b58check_encode(b"\x1c\xb8" + self.H).startswith("t1"))
        self.assertTrue(b58check_encode(b"\x41" + self.H).startswith("T"))

    def test_ambiguous_legacy_p2sh_lists_all_candidates(self):
        r = validate("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
        self.assertEqual({c.chain for c in r.candidates}, {"bitcoin", "bitcoin_cash", "litecoin"})
        self.assertEqual(r.primary.chain, "bitcoin")

    def test_unknown_version_reports_reason(self):
        r = validate(b58check_encode(b"\x99" + self.H))
        self.assertFalse(r.is_valid)
        self.assertIn("version byte", r.error)

    def test_cosmos_family_incl_high_first_5bit_group(self):
        # Regression: the earlier build rejected ~half of Cosmos addresses (it treated the first
        # 5-bit group as a SegWit version and required <= 16).
        for prog in (bytes(20), b"\xff" * 20):
            data = convertbits(prog, 8, 5, True)
            for hrp, chain in (("cosmos", "cosmos"), ("osmo", "osmosis"), ("juno", "juno")):
                r = validate(bech32_encode(hrp, data, "bech32"))
                self.assertTrue(r.is_valid, r.error)
                self.assertEqual(r.primary.chain, chain)

    def test_segwit_version_rules(self):
        prog = convertbits(bytes(20), 8, 5, True)
        # v0 must be Bech32; v0 encoded with Bech32m is invalid
        self.assertTrue(validate(bech32_encode("bc", [0] + prog, "bech32")).is_valid)
        self.assertFalse(validate(bech32_encode("bc", [0] + prog, "bech32m")).is_valid)
        # v1+ must be Bech32m
        prog32 = convertbits(bytes(32), 8, 5, True)
        self.assertTrue(validate(bech32_encode("bc", [1] + prog32, "bech32m")).is_valid)
        self.assertFalse(validate(bech32_encode("bc", [1] + prog32, "bech32")).is_valid)

    def test_uppercase_bech32_qr_form(self):
        r = validate("BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4")
        self.assertTrue(r.is_valid)
        self.assertEqual(r.normalized, "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        self.assertFalse(validate("Bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4").is_valid)  # mixed case


class TestTxHashes(unittest.TestCase):
    def test_hex64(self):
        h = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
        r = validate(h)
        self.assertTrue(r.is_valid)
        self.assertEqual(r.kind, "transaction_hash")
        self.assertIn("bitcoin", {c.chain for c in r.candidates})
        self.assertEqual(r.certainty, "format_only")

    def test_evm_tx_hash(self):
        r = validate("0x" + "ab" * 32)
        self.assertEqual(r.kind, "transaction_hash")
        self.assertIn("ethereum", {c.chain for c in r.candidates})

    def test_solana_signature(self):
        from address_validator import b58encode
        r = validate(b58encode(bytes(range(1, 65))))
        self.assertEqual(r.kind, "transaction_hash")
        self.assertEqual(r.primary.chain, "solana")


class TestNormalisationAndDiagnostics(unittest.TestCase):
    A = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

    def test_whitespace_quotes_zero_width_and_uri(self):
        for form in (f"  {self.A}\n", f'"{self.A}"', "\u200b" + self.A, f"bitcoin:{self.A}?amount=1&label=x",
                     f"{self.A}."):
            with self.subTest(form=form):
                self.assertTrue(validate(form).is_valid)
        self.assertTrue(validate("ethereum:0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed@1/transfer").is_valid)

    def test_lookalike_characters_are_named(self):
        r = validate(self.A.replace("1A1z", "1AIz", 1))  # capital I is not Base58
        self.assertFalse(r.is_valid)
        self.assertIn("I", r.error)
        self.assertIn("Base58", r.error)

    def test_checksum_failure_message(self):
        r = validate(self.A[:-1] + "b")
        self.assertFalse(r.is_valid)
        self.assertIn("checksum", r.error.lower())

    def test_ens_and_garbage_and_empty(self):
        self.assertEqual(validate("vitalik.eth").kind, "ens_name")
        for junk in ("", "   ", "invalid_address", "hello world", "0xZZZ", None, 12345):
            self.assertFalse(validate(junk).is_valid, junk)

    def test_internal_whitespace(self):
        self.assertIn("whitespace", validate(self.A[:10] + " " + self.A[10:]).error)

    def test_oversized_input_is_rejected_fast(self):
        t = time.time()
        r = validate("1" * 100_000)
        self.assertFalse(r.is_valid)
        self.assertLess(time.time() - t, 0.5)

    def test_to_dict_is_json_serialisable(self):
        import json
        json.dumps(validate(self.A).to_dict())
        json.dumps(validate("nonsense").to_dict())


if __name__ == "__main__":
    unittest.main(verbosity=2)
