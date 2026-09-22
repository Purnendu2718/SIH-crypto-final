"""RFC 3161 Trusted Timestamp Authority (TSA) Client.
Standard-library based client to request RFC 3161 timestamp tokens for manifest hashes.
Reference: RFC 3161, SIH26183 Defensible Evidence Architecture.
"""

import os
import urllib.request
import urllib.error
import logging
from typing import Optional

logger = logging.getLogger("cryptotrace.tsa")


def create_timestamp_request(digest_bytes: bytes) -> bytes:
    """Create a DER-encoded RFC 3161 TimeStampReq for a 32-byte SHA-256 digest.
    
    ASN.1 Structure:
    TimeStampReq ::= SEQUENCE {
        version          INTEGER  { v1(1) },
        messageImprint   MessageImprint {
            hashAlgorithm AlgorithmIdentifier (id-sha256 = 2.16.840.1.101.3.4.2.1),
            hashedMessage OCTET STRING
        },
        certReq          BOOLEAN DEFAULT FALSE
    }
    """
    if len(digest_bytes) != 32:
        raise ValueError(f"Expected 32-byte SHA-256 digest, got {len(digest_bytes)} bytes")

    # AlgorithmIdentifier: id-sha256 with NULL parameters
    oid_sha256 = bytes([
        0x30, 0x0D,
        0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
        0x05, 0x00,
    ])
    # MessageImprint: SEQUENCE { AlgorithmIdentifier, OCTET STRING (digest) }
    imprint_body = oid_sha256 + bytes([0x04, 0x20]) + digest_bytes
    msg_imprint = bytes([0x30, len(imprint_body)]) + imprint_body

    # version = 1, certReq = TRUE
    version = bytes([0x02, 0x01, 0x01])
    cert_req = bytes([0x01, 0x01, 0xFF])

    req_body = version + msg_imprint + cert_req
    req_der = bytes([0x30, len(req_body)]) + req_body
    return req_der


def request_rfc3161_timestamp(
    digest_bytes: bytes,
    tsa_url: Optional[str] = None,
    timeout: int = 5,
) -> Optional[bytes]:
    """Request an RFC 3161 timestamp token from a designated TSA server.
    
    Returns the binary timestamp response (.tsr) if successful, or None if TSA_URL
    is unset or unreachable. Never fakes a timestamp.
    """
    url = tsa_url or os.getenv("TSA_URL")
    if not url or not url.strip():
        logger.info("TSA_URL is not set. Evidence package will note 'not externally anchored'.")
        return None

    url = url.strip()
    try:
        req_payload = create_timestamp_request(digest_bytes)
        http_req = urllib.request.Request(
            url,
            data=req_payload,
            headers={
                "Content-Type": "application/timestamp-query",
                "Accept": "application/timestamp-reply",
                "User-Agent": "CryptoTrace-Sentinel-TSA/1.0",
            },
            method="POST",
        )

        with urllib.request.urlopen(http_req, timeout=timeout) as resp:
            if resp.status == 200:
                tsr_bytes = resp.read()
                logger.info(f"Successfully obtained RFC 3161 timestamp from {url} ({len(tsr_bytes)} bytes)")
                return tsr_bytes
            else:
                logger.warning(f"TSA server {url} returned HTTP status {resp.status}")
                return None
    except Exception as e:
        logger.warning(f"Unable to obtain RFC 3161 timestamp from {url}: {e}")
        return None
