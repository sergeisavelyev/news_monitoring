import hashlib


def compute_hash(title: str, url: str) -> str:
    """MD5(lower(strip(title)) + '|' + strip(url))"""
    normalized = title.lower().strip() + "|" + url.strip()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
