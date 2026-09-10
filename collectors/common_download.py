from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Iterable

import requests


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_session(user_agent: str) -> requests.Session:
    if not user_agent or "@" not in user_agent:
        raise ValueError("Use a descriptive SEC-compliant User-Agent containing a contact email.")
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
    })
    return session


def request_with_retry(session: requests.Session, url: str, *, timeout: int = 180,
                       delay: float = 0.2, attempts: int = 7,
                       stream: bool = False) -> requests.Response:
    last = None
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=timeout, stream=stream)
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                last = RuntimeError(f"HTTP {response.status_code}")
                time.sleep(delay * (2 ** min(attempt, 5)))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (2 ** min(attempt, 5)))
    raise RuntimeError(f"request failed: {url}: {last}")


def download_resumable(session: requests.Session, url: str, target: Path,
                       *, delay: float = 0.2, expected_min_bytes: int = 1,
                       overwrite: bool = False) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    if target.exists() and not overwrite:
        return {"url": url, "localFile": str(target), "status": "CACHED",
                "bytes": target.stat().st_size, "sha256": sha256_file(target)}
    resume_from = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    response = session.get(url, timeout=300, stream=True, headers=headers)
    if response.status_code == 416 and partial.exists():
        partial.replace(target)
    else:
        response.raise_for_status()
        append = resume_from > 0 and response.status_code == 206
        mode = "ab" if append else "wb"
        if not append and partial.exists():
            partial.unlink()
        with partial.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        partial.replace(target)
    if target.stat().st_size < expected_min_bytes:
        raise RuntimeError(f"download too small: {target} ({target.stat().st_size} bytes)")
    result = {"url": url, "localFile": str(target), "status": "DOWNLOADED",
              "bytes": target.stat().st_size, "sha256": sha256_file(target)}
    if target.suffix.lower() == ".zip":
        with zipfile.ZipFile(target) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(f"corrupt ZIP member {bad}: {target}")
            result["zipMembers"] = len(archive.namelist())
    time.sleep(delay)
    return result


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
