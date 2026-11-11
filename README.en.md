<div align="center">

# ziwei-analyze · Zi Wei Dou Shu Prediction Verification System

[![CI](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml/badge.svg)](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](./LICENSE)
[![Dataset: CC BY-SA 4.0](https://img.shields.io/badge/dataset-CC%20BY--SA%204.0-green.svg)](./DATASET-LICENSE)

[中文](./README.md) · **English**

[Try Online](https://guangbaobaozero.github.io/ziwei-analyze/) · [Quickstart](./docs/quickstart.md) · [Dataset Card](./DATA_CARD.md)

</div>

---

## What is this

A Zi Wei Dou Shu chart plotting and analysis toolkit with four modules: chart engine, knowledge base, prediction verification, and statistical reporting.

- **Chart Engine** — Node.js, zero dependencies, supports natal / decade / annual / monthly / daily / hourly layers
- **Knowledge Base** — 4,253 knowledge slices (CC BY-SA 4.0), covering all 14 major star systems, 12 palaces, patterns, transformations, and transit periods
- **Search & Batch Scripts** — Python, zero dependencies, keyword + optional vector semantic search
- **Verification Library** — Event capture, prediction grading, confidence calibration, pattern statistics
- **DSH Panel Plugin** — Optional, one-click visual panel for DeepSeek Harness users

## Core Capabilities

- **Six-layer chart plotting** — natal / decade / annual / monthly / daily / hourly, Node.js with zero dependencies
- **AI palace-by-palace analysis** — knowledge-base-driven, 12 independent palace analyses + synthesis + fusion
- **Prediction verification loop** — prediction queue → event capture → judgment → confidence calibration
- **Statistical reporting** — accuracy rates, tier statistics, pattern insights, monthly/annual cycles
- **Knowledge base search** — 4,253 slices covering stars, palaces, patterns, transformations
- **Vector semantic search** — optional faiss submodule

## Quick Start

\`\`\`bash
```bash
git clone https://github.com/GuangBaoBaoZero/ziwei-analyze.git
cd ziwei-analyze

# Self-check
python bin/selfcheck.py

# Plot a chart (requires Node.js ≥14)
node engine/paipan.js --year 1990 --month 8 --day 15 --hour 14 --gender male

# Search the knowledge base
python core/retrieve.py --star 紫微 --palace 命宫
```
\`\`\`

## Directory Structure

\`\`
```
├── engine/          # Chart engine (Node.js, zero dependencies)
├── core/            # Classification / search / input prep / transit engine / pattern verification
├── bin/             # Dispatch / validation / assembly / brief generation
├── verify/bin/      # Verification library (capture / grading / calibration / statistics)
├── data/            # Knowledge base: 4,253 slices (CC BY-SA 4.0)
├── docs/            # Guides / palace templates / brief specs / capture guide
├── vector/          # Vector semantic search submodule (optional faiss)
├── dsh-plugin/      # DSH visual panel plugin (optional)
└── engine/ziwei-pure.html  # Standalone web version (open in browser)
```
\`\`

## License

- Code: [MIT](./LICENSE)
- Knowledge Base Dataset: [CC BY-SA 4.0](./DATASET-LICENSE)
