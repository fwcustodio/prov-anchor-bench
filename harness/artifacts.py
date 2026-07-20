"""Derives ~20 pipeline artifacts from a public INMET/BDMEP weather CSV.

Raw copy, cleaning, monthly aggregates, features, train/test split, a
dependency-free classifier and its metrics. Every artifact is a file; its
SHA-256 is what gets anchored.

Input: harness/data/inmet.csv (semicolon-separated, latin-1 or utf-8, INMET
historical format with metadata rows before the header).
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import ARTIFACTS_DIR, DATA_DIR
from .prov import ArtifactInput, sha256_of_file


@dataclass(frozen=True)
class Row:
    date_iso: str
    temp: float
    humidity: float
    precipitation: float


@dataclass(frozen=True)
class PipelineArtifact:
    id: str
    sha256: str
    step_type: str
    used_ids: tuple[str, ...]
    path: Path

    def as_input(self) -> ArtifactInput:
        return ArtifactInput(
            id=self.id, sha256=self.sha256, step_type=self.step_type, used_ids=self.used_ids
        )


@dataclass(frozen=True)
class FeatureRow:
    day: str
    mean_temp: float
    delta_temp: float
    rain_next: int


def _parse_number(raw: str | None) -> float:
    if raw is None:
        return float("nan")
    cleaned = raw.strip().replace(",", ".")
    if cleaned == "" or cleaned == "-9999":
        return float("nan")
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def _load_rows(csv_path: Path) -> list[Row]:
    data = csv_path.read_bytes()
    try:
        text = data.decode("utf8")
        if "�" in text:
            raise UnicodeDecodeError("utf8", data, 0, 1, "replacement found")
    except UnicodeDecodeError:
        text = data.decode("latin1")
    lines = text.splitlines()

    header_index = next(
        (
            i
            for i, line in enumerate(lines)
            if "data" in line.lower() and ("temp" in line.lower() or "prec" in line.lower())
        ),
        -1,
    )
    if header_index < 0:
        raise ValueError(f"No header row found in {csv_path}")
    header_line = lines[header_index]
    sep = ";" if ";" in header_line else ","
    header = [column.strip().lower() for column in header_line.split(sep)]

    def find(predicate_terms: Sequence[str]) -> int:
        for index, name in enumerate(header):
            if all(term in name for term in predicate_terms):
                return index
        return -1

    date_col = next((i for i, h in enumerate(header) if h.startswith("data")), -1)
    temp_col = find(["temperatura", "bulbo"])
    if temp_col < 0:
        temp_col = find(["temp"])
    hum_col = find(["umidade"])
    prec_col = find(["precipita"])
    if date_col < 0 or temp_col < 0:
        raise ValueError(f"Missing date/temperature columns in {csv_path}")

    rows: list[Row] = []
    for line in lines[header_index + 1 :]:
        if line.strip() == "":
            continue
        cells = line.split(sep)

        def cell(index: int) -> str | None:
            return cells[index] if 0 <= index < len(cells) else None

        raw_date = (cell(date_col) or "").strip()
        date_iso = (
            "-".join(reversed(raw_date.split("/"))) if "/" in raw_date else raw_date
        )
        rows.append(
            Row(
                date_iso=date_iso,
                temp=_parse_number(cell(temp_col)),
                humidity=_parse_number(cell(hum_col)) if hum_col >= 0 else float("nan"),
                precipitation=_parse_number(cell(prec_col)) if prec_col >= 0 else float("nan"),
            )
        )
    return rows


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def _rows_to_csv(rows: Sequence[Row]) -> str:
    body = "\n".join(
        f"{r.date_iso};{r.temp};{r.humidity};{r.precipitation}" for r in rows
    )
    return f"date;temp;humidity;precipitation\n{body}\n"


def _feature_csv(rows: Sequence[FeatureRow]) -> str:
    body = "\n".join(
        f"{f.day};{f.mean_temp:.2f};{f.delta_temp:.2f};{f.rain_next}" for f in rows
    )
    return f"day;mean_temp;delta_temp;rain_next\n{body}\n"


def _write(
    artifacts: list[PipelineArtifact],
    artifact_id: str,
    step_type: str,
    used_ids: tuple[str, ...],
    file_name: str,
    content: str,
) -> None:
    path = ARTIFACTS_DIR / file_name
    path.write_text(content, encoding="utf8")
    artifacts.append(
        PipelineArtifact(
            id=artifact_id,
            sha256=sha256_of_file(path),
            step_type=step_type,
            used_ids=used_ids,
            path=path,
        )
    )


def build_artifacts(input_csv: Path | None = None) -> list[PipelineArtifact]:
    csv_path = input_csv if input_csv is not None else DATA_DIR / "inmet.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {csv_path}. See data/README.md for the download source."
        )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifacts: list[PipelineArtifact] = []

    # 01 raw / 02 clean
    raw = _load_rows(csv_path)
    _write(artifacts, "01-raw", "ingest", (), "01-raw.csv", _rows_to_csv(raw))
    clean = [r for r in raw if math.isfinite(r.temp)]
    _write(artifacts, "02-clean", "clean", ("01-raw",), "02-clean.csv", _rows_to_csv(clean))

    # 03..14 monthly aggregates (12 artifacts)
    by_month: dict[str, list[Row]] = {}
    for row in clean:
        by_month.setdefault(row.date_iso[:7], []).append(row)
    months = sorted(by_month.keys())[:12]
    for index, month in enumerate(months):
        bucket = by_month[month]
        artifact_id = f"03-agg-{index + 1:02d}"
        humid = [r.humidity for r in bucket if math.isfinite(r.humidity)]
        precip = sum(r.precipitation for r in bucket if math.isfinite(r.precipitation))
        content = (
            "month;mean_temp;mean_humidity;total_precipitation;n\n"
            f"{month};{_mean([r.temp for r in bucket]):.2f};"
            f"{_mean(humid):.2f};{precip:.1f};{len(bucket)}\n"
        )
        _write(artifacts, artifact_id, "aggregate", ("02-clean",), f"{artifact_id}.csv", content)

    # 15 features: day-over-day temperature delta, rain-next-day label
    daily: dict[str, list[Row]] = {}
    for row in clean:
        daily.setdefault(row.date_iso[:10], []).append(row)
    days = sorted(daily.keys())
    features: list[FeatureRow] = []
    for i in range(len(days) - 1):
        today = daily[days[i]]
        nxt = daily[days[i + 1]]
        prev_day = daily[days[i - 1]] if i > 0 else today
        mean_temp = _mean([r.temp for r in today])
        delta_temp = mean_temp - _mean([r.temp for r in prev_day])
        rain_next = (
            1
            if sum(r.precipitation for r in nxt if math.isfinite(r.precipitation)) > 0
            else 0
        )
        features.append(
            FeatureRow(day=days[i], mean_temp=mean_temp, delta_temp=delta_temp, rain_next=rain_next)
        )
    _write(artifacts, "15-features", "featurize", ("02-clean",), "15-features.csv", _feature_csv(features))

    # 16/17 chronological 80/20 split
    cut = int(len(features) * 0.8)
    train, test = features[:cut], features[cut:]
    _write(artifacts, "16-train", "split", ("15-features",), "16-train.csv", _feature_csv(train))
    _write(artifacts, "17-test", "split", ("15-features",), "17-test.csv", _feature_csv(test))

    # 18 model: class-conditional means classifier (dependency-free)
    rainy = [f for f in train if f.rain_next == 1]
    dry = [f for f in train if f.rain_next == 0]
    model: dict[str, object] = {
        "type": "class-conditional-means",
        "rainy": {
            "meanTemp": _mean([f.mean_temp for f in rainy]),
            "meanDelta": _mean([f.delta_temp for f in rainy]),
        },
        "dry": {
            "meanTemp": _mean([f.mean_temp for f in dry]),
            "meanDelta": _mean([f.delta_temp for f in dry]),
        },
        "priorRainy": len(rainy) / len(train) if train else 0.0,
    }
    _write(artifacts, "18-model", "train", ("16-train",), "18-model.json", json.dumps(model, indent=2) + "\n")

    # 19 metrics on the test split
    def distance(feature: FeatureRow, center: dict[str, float]) -> float:
        return abs(feature.mean_temp - center["meanTemp"]) + abs(
            feature.delta_temp - center["meanDelta"]
        )

    rainy_center = {"meanTemp": float(_mean([f.mean_temp for f in rainy])), "meanDelta": float(_mean([f.delta_temp for f in rainy]))}
    dry_center = {"meanTemp": float(_mean([f.mean_temp for f in dry])), "meanDelta": float(_mean([f.delta_temp for f in dry]))}
    correct = sum(
        1
        for f in test
        if (1 if distance(f, rainy_center) < distance(f, dry_center) else 0) == f.rain_next
    )
    metrics = {
        "testSize": len(test),
        "accuracy": correct / len(test) if test else float("nan"),
    }
    _write(artifacts, "19-metrics", "evaluate", ("18-model", "17-test"), "19-metrics.json", json.dumps(metrics, indent=2) + "\n")

    # 20 run config
    _write(
        artifacts,
        "20-config",
        "configure",
        (),
        "20-config.json",
        json.dumps({"input": "inmet.csv", "split": 0.8, "months": len(months)}, indent=2) + "\n",
    )

    manifest = [
        {"id": a.id, "stepType": a.step_type, "usedIds": list(a.used_ids), "sha256": a.sha256}
        for a in artifacts
    ]
    (ARTIFACTS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    return artifacts


if __name__ == "__main__":
    input_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    built = build_artifacts(input_arg)
    print(f"{len(built)} artifacts written to {ARTIFACTS_DIR}")
    for artifact in built:
        print(f"  {artifact.id}  {artifact.sha256[:16]}...")
