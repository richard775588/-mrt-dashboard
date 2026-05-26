"""
Background scheduler - runs ETL every 5 minutes.
Called once at app startup via Streamlit's cache.
"""
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from etl.pipeline import run_all, fetch_youbike, fetch_weather, fetch_aqi

_scheduler_started = False


def _scheduler_loop():
    """Run ETL for live data sources every 5 minutes."""
    while True:
        time.sleep(300)  # 5 minutes
        try:
            print("[Scheduler] Auto-refresh triggered")
            fetch_youbike()
            fetch_weather()
            fetch_aqi()
        except Exception as e:
            print(f"[Scheduler] Error: {e}")


def start_scheduler():
    global _scheduler_started
    if not _scheduler_started:
        t = threading.Thread(target=_scheduler_loop, daemon=True)
        t.start()
        _scheduler_started = True
        print("[Scheduler] Background refresh started (every 5 min)")
