#!/usr/bin/env bash
# SPX Paper Trader — server launcher.
# Recommended next to Combo Trader, sharing its Schwab tokens read-compatibly:
#   export LOGICON_TOKENS_FILE=/path/to/combo-trader-tv/tokens.json
#   export PAPER_HOST=0.0.0.0   # to open the dashboard from another machine
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
exec python3 paper_dashboard.py
