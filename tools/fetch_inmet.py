"""Provides the exact INMET input used by the pilot and checks its SHA-256.

Source: INMET historical data portal, yearly archive 2003, station A901
(CUIABA - MT). A verified copy of the raw file is versioned under data/inmet/
(public open data) so verification does not depend on the portal being up;
the portal is used only when that copy is missing. The CSV is written to
harness/data/inmet.csv.

Usage: python -m tools.fetch_inmet
"""

from __future__ import annotations

import hashlib
import io
import sys
import time
import zipfile
from pathlib import Path
from typing import Final

import requests

from harness.config import DATA_DIR, REPO_ROOT

ARCHIVE_URL: Final[str] = "https://portal.inmet.gov.br/uploads/dadoshistoricos/2003.zip"
STATION_MARKER: Final[str] = "A901_CUIABA"
EXPECTED_SHA256: Final[str] = "0cecf2fdf3a9c26db24289d956b13522d9fc763b5a503d142df784069a58ee0b"
VERSIONED_COPY: Final[Path] = REPO_ROOT / "data" / "inmet" / "INMET_CO_MT_A901_CUIABA_01-01-2003_A_31-12-2003.CSV"
# The portal rejects requests without a browser-like user agent.
_HEADERS: Final[dict[str, str]] = {"User-Agent": "Mozilla/5.0 (prov-anchor-bench data fetch)"}


def download_archive(attempts: int = 5) -> bytes:
    """The portal intermittently resets connections; retry with backoff."""
    last_error: requests.RequestException | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(ARCHIVE_URL, headers=_HEADERS, timeout=300)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            last_error = error
            print(f"  attempt {attempt}/{attempts} failed: {type(error).__name__}", file=sys.stderr)
            time.sleep(3.0 * attempt)
    raise RuntimeError(
        f"could not download {ARCHIVE_URL} after {attempts} attempts ({last_error}). "
        "Download it manually in a browser, extract the A901_CUIABA CSV and save it "
        "as harness/data/inmet.csv; this script then verifies its SHA-256."
    )


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
    if VERSIONED_COPY.exists():
        member, content = VERSIONED_COPY.name, VERSIONED_COPY.read_bytes()
        print(f"using versioned copy {VERSIONED_COPY.relative_to(REPO_ROOT).as_posix()}")
    else:
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
