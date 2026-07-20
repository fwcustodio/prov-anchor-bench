# Input data

The pilot derives its artifacts from a public INMET (Brazilian National Institute
of Meteorology) historical weather CSV.

1. Download a station file from the INMET historical data portal:
   https://portal.inmet.gov.br/dadoshistoricos (yearly zips, one CSV per station),
   or export a series from BDMEP: https://bdmep.inmet.gov.br/
2. Save it as `harness/data/inmet.csv`.

Any INMET station/year works: the parser skips the metadata preamble and reads the
date, temperature, humidity and precipitation columns. Raw CSVs are git-ignored;
only their derived artifact hashes are anchored.
