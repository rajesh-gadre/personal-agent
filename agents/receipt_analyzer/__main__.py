"""Run the receipt watcher as a standalone process.

Usage:
    python -m agents.receipt_analyzer.watcher

Or via console script (after pip install -e .):
    receipt-watcher
"""
from agents.receipt_analyzer.watcher import run_watcher

if __name__ == "__main__":
    run_watcher()
