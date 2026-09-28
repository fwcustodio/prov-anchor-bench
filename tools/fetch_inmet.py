"""Downloads the exact INMET input used by the pilot and checks its SHA-256.

Source: INMET historical data portal, yearly archive 2003, station A901
(CUIABA - MT). The extracted CSV is written to harness/data/inmet.csv.

Usage: python -m tools.fetch_inmet
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from typing import Final

import requests

from harness.config import DATA_DIR

ARCHIVE_URL: Final[str] = "https://portal.inmet.gov.br/uploads/dadoshistoricos/2003.zip"
STATION_MARKER: Final[str] = "A901_CUIABA"
EXPECTED_SHA256: Final[str] = "0cecf2fdf3a9c26db24289d956b13522d9fc763b5a503d142df784069a58ee0b"
# The portal rejects requests without a browser-like user agent.
_HEADERS: Final[dict[str, str]] = {"User-Agent": "Mozilla/5.0 (prov-anchor-bench data fetch)"}


def download_archive() -> bytes:
    response = requests.get(ARCHIVE_URL, headers=_HEADERS, timeout=300)
    response.raise_for_status()
    return response.content


def extract_station(archive: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = [name for name in bundle.namelist() if STATION_MARKER in name.upper()]
        if len(members) != 1:
            raise ValueError(f"expected one {STATION_MARKER} file in the archive, found {members}")
        return members[0], bundle.read(members[0])


def main() -> None:
    target = DATA_DIR / "inmet.csv"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED_SHA256:
        print(f"{target} already present and verified (SHA-256 {EXPECTED_SHA256[:16]}...)")
        return
    print(f"downloading {ARCHIVE_URL} ...")
    member, content = extract_station(download_archive())
    digest = hashlib.sha256(content).hexdigest()
    if digest != EXPECTED_SHA256:
        print(f"SHA-256 mismatch for {member}: {digest} != {EXPECTED_SHA256}", file=sys.stderr)
        sys.exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    print(f"{member} -> {target} (SHA-256 verified)")


if __name__ == "__main__":
    main()
