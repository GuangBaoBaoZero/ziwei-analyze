<div align="center">

# ziwei-analyze · Zi Wei Dou Shu Forecast & Verification System

[![CI](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml/badge.svg)](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](./LICENSE)
[![Dataset: CC BY-SA 4.0](https://img.shields.io/badge/dataset-CC%20BY--SA%204.0-green.svg)](./DATASET-LICENSE)

[中文](./README.md) · **English**

[Quick Start](./docs/quickstart.md) · [Dataset Card](./DATA_CARD.md)

</div>

---

A Zi Wei Dou Shu analysis system built around a **forecast → verification** loop: the chart issues a forecast (directional assertion), reality supplies the fact (returns / events), and the system grades it automatically into a track-record ledger. Paired with hybrid search over 73 classical texts and five-layer quote verification — every claim and quotation is traceable.

## Who It's For

- **ZWDS learners & researchers**: analysis with traceable sources (4,253 plain-language knowledge slices + 73 classical texts) and quantified verification of forecasting skill
- **AI/agent practitioners**: a verifiable ZWDS toolkit for agents — sourced retrieval, verified quotations, graded ledgers
- **Data enthusiasts**: the forecast-verification loop is a natural empirical playground (hit rate / calibration / confidence-stratified stats)

## Core Features (as implemented in bin/ and verify/)

### 1. The Forecast–Verification Loop (the soul)
- **Enqueue forecasts**: directional assertions in briefs are extracted into a pending queue with conditions and hit criteria
- **Auto-grading**: after each trading day, actual returns are compared automatically (total ≥ 0 = hit)
- **Track-record ledger**: cumulative xlsx ledger (direction / confidence / result / accuracy)
- **Beyond P&L**: eight event categories (trading / travel / health / disputes / accidents / mood / decisions / relationships)

### 2. Classical Library: 73 Texts + Hybrid Search (works out of the box)
- 73 curated classics (incl. the full Zizhi Tongjian 294 juan, Ming Shi 153, Yuan Shi 78), public domain
- Hybrid retrieval: FAISS semantic vectors + literal substring matching (punctuation- and variant-normalized), RRF fused at book level
- Prebuilt index (20,969 chunks) + bge model shipped in-package — zero download, zero network
- One-command setup: `python bin/setup_vector.py` (agent can run it automatically)

### 3. Quote Verification: five-layer fuzzy matching
`classics_verify.py --quote "..." --book ...` — exact → whitespace → variant → cross-line → particle layers; reports book + line on hit, nearest diff on miss. No room for fabricated quotations.

### 4. Four Orchestrators: daily / weekly / monthly / yearly pipelines
`ziwei_daily.py` (13 steps) / `ziwei_monthly.py` / `ziwei_yearly.py` / `weekly_check.py` — idempotent, resumable (--from-step), JSON logs.

### 5. Chart Engine + Plain-Language Knowledge Base
- Node.js engine, zero deps: `node engine/paipan.js --birth "1995-06-15 12:30" --gender male`
- 4,253 knowledge slices (CC BY-SA 4.0), FAISS+BM25 hybrid search (prebuilt index included)
- Optional semantic search: faiss + bundled local model, no network

## Quick Start

Prerequisites: Node.js ≥ 16 (engine); Python ≥ 3.10 (pipelines).

> **Windows notes**: ① If `python` is not found, use `py` instead (or tick "Add Python to PATH" during installation); ② If Chinese characters look garbled in the console, set `PYTHONUTF8=1` (or run `chcp 65001`) first.

```bash
git clone https://github.com/GuangBaoBaoZero/ziwei-analyze.git
cd ziwei-analyze

# ① Chart (zero deps)
node engine/paipan.js --birth "1995-06-15 12:30" --gender male
# → full 12-palace chart JSON with majors and transformations

# ② One-command retrieval setup
python bin/setup_vector.py
# → [1/5] deps … [5/5] live query self-test → all ready

# ③ Hybrid search
python bin/classics_search.py --keywords "欲速则不达"
# → Analects / chunk 18 / …子曰："无欲速，无见小利。欲速则不达…"

# ④ Quote verification
python bin/classics_verify.py --quote "山下有雷，颐" --book 周易
# → [HIT] Zhouyi, exact layer, line 578
```

See [docs/quickstart.md](docs/quickstart.md).

## Numbers

| Item | Value |
|---|---|
| Classical texts | 73 (public domain) |
| Knowledge slices | 4,253 |
| Retrieval index | 20,969 chunks (768 chars/chunk) |
| Quote verification | 5 layers |
| Build assertions | 14/14 |
| Package size | ~290 MB (model + index prebuilt) |

## Limitations (stated honestly)

- Semantic search needs `pip install faiss-cpu` etc. (auto-installed by setup_vector.py); without it, zero-dep literal txt search still works (auto fallback)
- Track records accumulate from your own verification data feed — the ledger starts empty
- Brief generation requires your LLM as the writer; this repo provides the toolchain and templates (docs/brief_prompt_template.md)
- Trade calendar auto-update requires akshare: `pip install akshare` (auto-attempted by setup / daily pipeline); without it the bundled calendar (through 2027-11) is used, and out-of-range dates are conservatively treated as closed
- Classical texts are modern edited editions (punctuated, simplified); retrieval normalizes both sides

## License

- Code: [MIT](LICENSE)
- Knowledge dataset: [CC BY-SA 4.0](DATASET-LICENSE)
- Classical texts (data/classics/): public domain
- Retrieval model bge-small-zh-v1.5: BAAI, MIT License (bundled)
