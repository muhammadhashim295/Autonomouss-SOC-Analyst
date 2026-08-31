"""Skill 6a — AlienVault OTX IOC enrichment.

Queries the OTX API for each IOC (IP, domain, hash) found in an alert's
payload and returns threat-intelligence matches.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import requests

from app.core.config import settings

_OTX_BASE = "https://otx.alienvault.com/api/v1"

# ── IOC extraction ──────────────────────────────────────────────────────

_IP_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|co|ws|onion|info|biz|xyz|top|ru|cn|uk|de|nl|cc|pw)\b"
)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")

_RFC1918 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def _is_public_ip(addr: str) -> bool:
    """Return True if the IP is not RFC-1918 private."""
    try:
        ip = ipaddress.ip_address(addr)
        return not any(ip in net for net in _RFC1918)
    except ValueError:
        return False


def extract_iocs(payload: dict[str, Any]) -> dict[str, list[str]]:
    """Extract IOCs from the alert payload (recursive text scan)."""
    text = str(payload)
    # Use dict.fromkeys for dedup to avoid set() hashing issues
    ips = list(dict.fromkeys(str(m) for m in _IP_RE.findall(text)))
    domains = list(dict.fromkeys(str(m) for m in _DOMAIN_RE.findall(text)))
    hashes = list(dict.fromkeys(str(m) for m in _HASH_RE.findall(text)))

    # Filter to public IPs only for OTX lookup
    public_ips = [ip for ip in ips if _is_public_ip(ip)]

    # Also grab explicit iocs field if present
    explicit = payload.get("iocs", [])
    for item in explicit:
        if _IP_RE.match(item) and _is_public_ip(item):
            if item not in public_ips:
                public_ips.append(item)
        elif _DOMAIN_RE.match(item):
            if item not in domains:
                domains.append(item)

    return {"ips": public_ips, "domains": domains, "hashes": hashes}


# ── OTX lookups ──────────────────────────────────────────────────────────

def _otx_get(path: str) -> dict[str, Any] | None:
    """Query a single OTX endpoint, return JSON or None on failure."""
    key = settings.otx_api_key
    if not key:
        return None

    headers = {"X-OTX-API-KEY": key}
    try:
        resp = requests.get(
            f"{_OTX_BASE}{path}",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


def _lookup_ip(ip: str) -> dict[str, Any]:
    """Look up an IP in OTX."""
    result: dict[str, Any] = {"ip": ip, "reputation": None, "pulses": [], "malware": False}

    data = _otx_get(f"/indicators/IPv4/{ip}/general")
    if data:
        result["reputation"] = data.get("reputation", 0)
        result["country"] = data.get("country_name", "unknown")
        result["asn"] = data.get("asn", "unknown")
        result["pulse_count"] = data.get("pulse_info", {}).get("count", 0)

        # Check sections for malware indicators
        sections = data.get("sections", [])
        if "malware" in sections:
            result["malware"] = True

    return result


def _lookup_domain(domain: str) -> dict[str, Any]:
    """Look up a domain in OTX."""
    result: dict[str, Any] = {"domain": domain, "reputation": None, "pulses": []}

    data = _otx_get(f"/indicators/domain/{domain}/general")
    if data:
        result["reputation"] = data.get("reputation", 0)
        result["pulse_count"] = data.get("pulse_info", {}).get("count", 0)
        result["alexa_rank"] = data.get("alexa", None)

    return result


def _lookup_hash(file_hash: str) -> dict[str, Any]:
    """Look up a file hash in OTX."""
    result: dict[str, Any] = {"hash": file_hash, "malware": False, "pulses": []}

    data = _otx_get(f"/indicators/file/{file_hash}/general")
    if data:
        result["malware"] = data.get("malware", {}).get("count", 0) > 0
        result["file_type"] = data.get("type", "unknown")
        result["pulse_count"] = data.get("pulse_info", {}).get("count", 0)

    return result


# ── Public API ───────────────────────────────────────────────────────────

def enrich_iocs(payload: dict[str, Any]) -> dict[str, Any]:
    """Run OTX enrichment on all IOCs found in the alert payload.

    Returns a structured report with matches for each IOC type.
    """
    iocs = extract_iocs(payload)
    results: dict[str, Any] = {
        "iocs_found": iocs,
        "otx_available": bool(settings.otx_api_key),
        "ip_results": [],
        "domain_results": [],
        "hash_results": [],
        "threat_summary": "",
    }

    if not settings.otx_api_key:
        results["threat_summary"] = "OTX API key not configured — enrichment skipped."
        return results

    # Look up each IOC
    for ip in iocs["ips"][:5]:  # Cap at 5 to respect rate limits
        results["ip_results"].append(_lookup_ip(ip))

    for domain in iocs["domains"][:5]:
        results["domain_results"].append(_lookup_domain(domain))

    for h in iocs["hashes"][:3]:
        results["hash_results"].append(_lookup_hash(h))

    # Build summary
    threats = []
    for ip_r in results["ip_results"]:
        if ip_r.get("reputation", 0) and ip_r["reputation"] < 50:
            threats.append(f"IP {ip_r['ip']} has low reputation (score: {ip_r['reputation']})")
        if ip_r.get("malware"):
            threats.append(f"IP {ip_r['ip']} associated with malware")

    for dom_r in results["domain_results"]:
        if dom_r.get("reputation", 0) and dom_r["reputation"] < 50:
            threats.append(f"Domain {dom_r['domain']} has low reputation")

    for hash_r in results["hash_results"]:
        if hash_r.get("malware"):
            threats.append(f"Hash {hash_r['hash'][:16]}... flagged as malware")

    if threats:
        results["threat_summary"] = " | ".join(threats)
    elif iocs["ips"] or iocs["domains"] or iocs["hashes"]:
        results["threat_summary"] = "No OTX threat matches found for extracted IOCs."
    else:
        results["threat_summary"] = "No public IOCs found in alert payload."

    return results
