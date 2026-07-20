import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ARTIFACTS_DIR, DATA_DIR } from "./config.js";
import { sha256OfFile, type ArtifactInput } from "./prov.js";

/**
 * Derives ~20 pipeline artifacts from a public INMET/BDMEP weather CSV:
 * raw copy, cleaning, monthly aggregates, features, train/test split, a
 * dependency-free linear model and its metrics. Every artifact is a file;
 * its SHA-256 is what gets anchored.
 *
 * Input: harness/data/inmet.csv (semicolon-separated, latin-1 or utf-8,
 * INMET historical format with metadata rows before the header).
 */

interface Row {
  readonly dateIso: string;
  readonly temp: number;
  readonly humidity: number;
  readonly precipitation: number;
}

export interface PipelineArtifact extends ArtifactInput {
  readonly path: string;
}

function detectSeparator(headerLine: string): string {
  return headerLine.includes(";") ? ";" : ",";
}

function parseNumber(raw: string | undefined): number {
  if (raw === undefined) return Number.NaN;
  const cleaned = raw.trim().replace(",", ".");
  if (cleaned === "" || cleaned === "-9999") return Number.NaN;
  return Number(cleaned);
}

function loadRows(csvPath: string): Row[] {
  const buffer = readFileSync(csvPath);
  let text = buffer.toString("utf8");
  if (text.includes("�")) text = buffer.toString("latin1");
  const lines = text.split(/\r?\n/);

  const headerIndex = lines.findIndex(
    (line) => /data/i.test(line) && (/temp/i.test(line) || /prec/i.test(line)),
  );
  if (headerIndex < 0) throw new Error(`No header row found in ${csvPath}`);
  const headerLine = lines[headerIndex];
  if (headerLine === undefined) throw new Error("unreachable");
  const sep = detectSeparator(headerLine);
  const header = headerLine.split(sep).map((h) => h.trim().toLowerCase());

  const dateCol = header.findIndex((h) => h.startsWith("data"));
  const tempCol = header.findIndex((h) => h.includes("temperatura") && h.includes("bulbo"));
  const tempColFallback = header.findIndex((h) => h.includes("temp"));
  const humCol = header.findIndex((h) => h.includes("umidade"));
  const precCol = header.findIndex((h) => h.includes("precipita"));
  const temperatureCol = tempCol >= 0 ? tempCol : tempColFallback;
  if (dateCol < 0 || temperatureCol < 0) {
    throw new Error(`Missing date/temperature columns in ${csvPath}`);
  }

  const rows: Row[] = [];
  for (const line of lines.slice(headerIndex + 1)) {
    if (line.trim() === "") continue;
    const cells = line.split(sep);
    const rawDate = cells[dateCol]?.trim() ?? "";
    const dateIso = rawDate.includes("/")
      ? rawDate.split("/").reverse().join("-")
      : rawDate.replaceAll("/", "-");
    rows.push({
      dateIso,
      temp: parseNumber(cells[temperatureCol]),
      humidity: humCol >= 0 ? parseNumber(cells[humCol]) : Number.NaN,
      precipitation: precCol >= 0 ? parseNumber(cells[precCol]) : Number.NaN,
    });
  }
  return rows;
}

function writeArtifact(
  artifacts: PipelineArtifact[],
  id: string,
  stepType: string,
  usedIds: readonly string[],
  fileName: string,
  content: string,
): void {
  const path = join(ARTIFACTS_DIR, fileName);
  writeFileSync(path, content, "utf8");
  artifacts.push({ id, stepType, usedIds, path, sha256: sha256OfFile(path) });
}

function rowsToCsv(rows: readonly Row[]): string {
  const body = rows
    .map((r) => `${r.dateIso};${r.temp};${r.humidity};${r.precipitation}`)
    .join("\n");
  return `date;temp;humidity;precipitation\n${body}\n`;
}

function mean(values: readonly number[]): number {
  if (values.length === 0) return Number.NaN;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function buildArtifacts(inputCsv?: string): PipelineArtifact[] {
  const csvPath = inputCsv ?? join(DATA_DIR, "inmet.csv");
  if (!existsSync(csvPath)) {
    throw new Error(`Input CSV not found: ${csvPath}. See data/README.md for the download source.`);
  }
  mkdirSync(ARTIFACTS_DIR, { recursive: true });
  const artifacts: PipelineArtifact[] = [];

  // 01 raw
  const raw = loadRows(csvPath);
  writeArtifact(artifacts, "01-raw", "ingest", [], "01-raw.csv", rowsToCsv(raw));

  // 02 clean: drop rows without a valid temperature
  const clean = raw.filter((r) => Number.isFinite(r.temp));
  writeArtifact(artifacts, "02-clean", "clean", ["01-raw"], "02-clean.csv", rowsToCsv(clean));

  // 03..14 monthly aggregates (12 artifacts)
  const byMonth = new Map<string, Row[]>();
  for (const row of clean) {
    const month = row.dateIso.slice(0, 7);
    const bucket = byMonth.get(month) ?? [];
    bucket.push(row);
    byMonth.set(month, bucket);
  }
  const months = [...byMonth.keys()].sort().slice(0, 12);
  const monthlyIds: string[] = [];
  months.forEach((month, index) => {
    const bucket = byMonth.get(month) ?? [];
    const id = `03-agg-${String(index + 1).padStart(2, "0")}`;
    monthlyIds.push(id);
    const content =
      `month;mean_temp;mean_humidity;total_precipitation;n\n` +
      `${month};${mean(bucket.map((r) => r.temp)).toFixed(2)};` +
      `${mean(bucket.filter((r) => Number.isFinite(r.humidity)).map((r) => r.humidity)).toFixed(2)};` +
      `${bucket
        .filter((r) => Number.isFinite(r.precipitation))
        .reduce((a, r) => a + r.precipitation, 0)
        .toFixed(1)};${bucket.length}\n`;
    writeArtifact(artifacts, id, "aggregate", ["02-clean"], `${id}.csv`, content);
  });

  // 15 features: day-over-day temperature delta, rain-next-day label
  const daily = new Map<string, Row[]>();
  for (const row of clean) {
    const day = row.dateIso.slice(0, 10);
    const bucket = daily.get(day) ?? [];
    bucket.push(row);
    daily.set(day, bucket);
  }
  const days = [...daily.keys()].sort();
  interface FeatureRow {
    readonly day: string;
    readonly meanTemp: number;
    readonly deltaTemp: number;
    readonly rainNext: 0 | 1;
  }
  const features: FeatureRow[] = [];
  for (let i = 0; i + 1 < days.length; i += 1) {
    const today = daily.get(days[i] ?? "") ?? [];
    const next = daily.get(days[i + 1] ?? "") ?? [];
    const meanTemp = mean(today.map((r) => r.temp));
    const prevDay = i > 0 ? daily.get(days[i - 1] ?? "") ?? [] : today;
    const deltaTemp = meanTemp - mean(prevDay.map((r) => r.temp));
    const rainNext: 0 | 1 =
      next.filter((r) => Number.isFinite(r.precipitation)).reduce((a, r) => a + r.precipitation, 0) >
      0
        ? 1
        : 0;
    features.push({ day: days[i] ?? "", meanTemp, deltaTemp, rainNext });
  }
  writeArtifact(
    artifacts,
    "15-features",
    "featurize",
    ["02-clean"],
    "15-features.csv",
    `day;mean_temp;delta_temp;rain_next\n${features
      .map((f) => `${f.day};${f.meanTemp.toFixed(2)};${f.deltaTemp.toFixed(2)};${f.rainNext}`)
      .join("\n")}\n`,
  );

  // 16/17 train-test split (chronological 80/20)
  const cut = Math.floor(features.length * 0.8);
  const train = features.slice(0, cut);
  const test = features.slice(cut);
  const featureCsv = (rows: readonly FeatureRow[]): string =>
    `day;mean_temp;delta_temp;rain_next\n${rows
      .map((f) => `${f.day};${f.meanTemp.toFixed(2)};${f.deltaTemp.toFixed(2)};${f.rainNext}`)
      .join("\n")}\n`;
  writeArtifact(artifacts, "16-train", "split", ["15-features"], "16-train.csv", featureCsv(train));
  writeArtifact(artifacts, "17-test", "split", ["15-features"], "17-test.csv", featureCsv(test));

  // 18 model: class-conditional means classifier (dependency-free)
  const rainy = train.filter((f) => f.rainNext === 1);
  const dry = train.filter((f) => f.rainNext === 0);
  const model = {
    type: "class-conditional-means",
    rainy: { meanTemp: mean(rainy.map((f) => f.meanTemp)), meanDelta: mean(rainy.map((f) => f.deltaTemp)) },
    dry: { meanTemp: mean(dry.map((f) => f.meanTemp)), meanDelta: mean(dry.map((f) => f.deltaTemp)) },
    priorRainy: train.length > 0 ? rainy.length / train.length : 0,
  };
  writeArtifact(
    artifacts,
    "18-model",
    "train",
    ["16-train"],
    "18-model.json",
    `${JSON.stringify(model, null, 2)}\n`,
  );

  // 19 metrics on the test split
  const distance = (f: FeatureRow, c: { meanTemp: number; meanDelta: number }): number =>
    Math.abs(f.meanTemp - c.meanTemp) + Math.abs(f.deltaTemp - c.meanDelta);
  let correct = 0;
  for (const f of test) {
    const predicted: 0 | 1 = distance(f, model.rainy) < distance(f, model.dry) ? 1 : 0;
    if (predicted === f.rainNext) correct += 1;
  }
  const metrics = {
    testSize: test.length,
    accuracy: test.length > 0 ? correct / test.length : Number.NaN,
  };
  writeArtifact(
    artifacts,
    "19-metrics",
    "evaluate",
    ["18-model", "17-test"],
    "19-metrics.json",
    `${JSON.stringify(metrics, null, 2)}\n`,
  );

  // 20 run config
  writeArtifact(
    artifacts,
    "20-config",
    "configure",
    [],
    "20-config.json",
    `${JSON.stringify({ input: "inmet.csv", split: 0.8, months: months.length }, null, 2)}\n`,
  );

  const manifest = artifacts.map(({ id, stepType, usedIds, sha256 }) => ({ id, stepType, usedIds, sha256 }));
  writeFileSync(join(ARTIFACTS_DIR, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return artifacts;
}

const isMain = process.argv[1]?.endsWith("artifacts.ts") ?? false;
if (isMain) {
  const artifacts = buildArtifacts(process.argv[2]);
  console.log(`${artifacts.length} artifacts written to ${ARTIFACTS_DIR}`);
  for (const a of artifacts) console.log(`  ${a.id}  ${a.sha256.slice(0, 16)}...`);
}
