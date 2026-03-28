from apscheduler.schedulers.background import BackgroundScheduler

from fetcher import fetch_all_feeds

_scheduler = BackgroundScheduler()


def start_scheduler() -> None:
    _scheduler.add_job(fetch_all_feeds, "interval", minutes=30, id="fetch_all_feeds")
    _scheduler.start()


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown()
