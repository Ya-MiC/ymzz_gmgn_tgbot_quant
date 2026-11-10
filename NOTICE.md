# Third-party notices

This repository's original code is MIT (see LICENSE). The backtest engine is original. It does not import or vendor the libraries below.

| Project | URL | Commit checked 2026-11-10 | License | Role here |
|---|---|---|---|---|
| kernc/backtesting.py | https://github.com/kernc/backtesting.py | `ca2e2611621e472542ba90f7243a1fa06a7d7108` (2026-08-05) | AGPL-3.0 | Reference only. Not installed. Not a dependency. |
| streamlit/streamlit | https://github.com/streamlit/streamlit | `86edf082ae9f4bd7fd9d5f45ab9bdd872709daa2` (2026-11-09) | Apache-2.0 | Dependency for the local dashboard. |
| plotly/plotly.py | https://github.com/plotly/plotly.py | `3c1aeba0a90ef6f7a32fd35a48338ef7ee349d93` (2026-11-06) | MIT | Dependency for the Streamlit charts. The static preview is SVG and does not load Plotly. |
| GMGNAI/gmgn-skills | https://github.com/GMGNAI/gmgn-skills | `6a04e1f00b5463cfc965e41003ca0c7c2db5b69f` (2026-10-29) | MIT | Reference only. Not a history archive and not imported. |
| polakowo/vectorbt | https://github.com/polakowo/vectorbt | `07f5e85e83a5286c396f4ecfd55dfaa05f25442d` (2026-11-08) | Apache-2.0 plus Commons Clause (`LICENSE.md`; GitHub SPDX `NOASSERTION`) | Not used. |
| mementum/backtrader | https://github.com/mementum/backtrader | `b853d7c90b6721476eb5a5ea3135224e33db1f14` (2023-04-19; repository metadata push 2024-08-19) | GPL-3.0 | Not used. |

pandas is BSD-3-Clause and pytest is MIT; exact installed versions are in `requirements.txt`.

Market data snapshots are not licensed as a data product. See `data/cache/README.md`. Attribute the OHLCV source as Powered by CoinGecko.
