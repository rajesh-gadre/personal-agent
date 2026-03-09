import logging
import signal
import sys
import threading
import time
from pathlib import Path

from shared.config.settings import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".pdf", ".webp", ".gif"}


def _is_receipt_file(path: Path) -> bool:
    """Check if a file is a supported receipt file."""
    return (
        path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.startswith(".")
    )


def _process_file(file_path: Path) -> None:
    """Process a single receipt file through the manager."""
    from agents.receipt_analyzer.manager import ReceiptManager

    mgr = ReceiptManager()
    mgr.init()

    logger.info(f"Watcher: processing {file_path.name}")
    try:
        result = mgr.analyze(str(file_path))
        if result.get("error"):
            logger.error(f"Watcher: failed to process {file_path.name}: {result['error']}")
        else:
            file_path.unlink()
            logger.info(f"Watcher: staged {file_path.name} (id={result.get('staging_id')})")
    except Exception as e:
        logger.error(f"Watcher: exception processing {file_path.name}: {e}")


def _scan_existing(watch_dir: Path) -> None:
    """Process any files already in the watch folder."""
    for f in watch_dir.iterdir():
        if _is_receipt_file(f):
            _process_file(f)


# ── Event-based watcher (watchdog) ──


def _create_event_observer(watch_dir: Path):
    """Create a watchdog Observer with a receipt file handler."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class ReceiptFileHandler(FileSystemEventHandler):
        """Reacts to new receipt files in the watch folder."""

        def on_created(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if not _is_receipt_file(path):
                return
            # Wait for file write to complete (copy/move may not be instant)
            time.sleep(2)
            if path.exists():
                _process_file(path)

        def on_moved(self, event):
            if event.is_directory:
                return
            path = Path(event.dest_path)
            if not _is_receipt_file(path):
                return
            time.sleep(2)
            if path.exists():
                _process_file(path)

    observer = Observer()
    observer.schedule(ReceiptFileHandler(), str(watch_dir), recursive=False)
    return observer


# ── Polling-based watcher (legacy fallback) ──


def _poll_loop(watch_dir: Path) -> None:
    """Polling loop that scans the watch folder periodically."""
    interval = settings.receipt_watch_interval_seconds
    logger.info(f"Watcher: polling {watch_dir} every {interval}s")
    while True:
        try:
            _scan_existing(watch_dir)
        except Exception as e:
            logger.error(f"Watcher: error in poll loop: {e}")
        time.sleep(interval)


# ── Entry points ──


def run_watcher() -> None:
    """Run watcher as a blocking main process. Use for standalone execution."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    watch_dir = Path(settings.receipt_watch_folder).expanduser()
    watch_dir.mkdir(parents=True, exist_ok=True)
    mode = getattr(settings, "receipt_watcher_mode", "event")

    # Process files already in folder
    logger.info(f"Watcher: scanning existing files in {watch_dir}")
    _scan_existing(watch_dir)

    if mode == "event":
        logger.info(f"Watcher: monitoring {watch_dir} (event mode)")
        observer = _create_event_observer(watch_dir)
        observer.start()

        def _shutdown(signum, frame):
            logger.info("Watcher: shutting down...")
            observer.stop()
            observer.join()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            observer.join()
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
    else:
        logger.info(f"Watcher: monitoring {watch_dir} (poll mode)")
        _poll_loop(watch_dir)


_watcher_thread: threading.Thread | None = None


def start_watcher() -> None:
    """Start the watcher in a background thread (for use inside Streamlit)."""
    global _watcher_thread
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return

    watch_dir = Path(settings.receipt_watch_folder).expanduser()
    watch_dir.mkdir(parents=True, exist_ok=True)
    mode = getattr(settings, "receipt_watcher_mode", "event")

    # Scan existing files first
    _scan_existing(watch_dir)

    if mode == "event":
        observer = _create_event_observer(watch_dir)
        observer.daemon = True
        observer.start()
        _watcher_thread = observer  # Observer is a Thread subclass
        logger.info(f"Watcher: background event watcher started on {watch_dir}")
    else:
        _watcher_thread = threading.Thread(
            target=_poll_loop, args=(watch_dir,), daemon=True, name="receipt-watcher"
        )
        _watcher_thread.start()
        logger.info(f"Watcher: background poll watcher started on {watch_dir}")


if __name__ == "__main__":
    run_watcher()
