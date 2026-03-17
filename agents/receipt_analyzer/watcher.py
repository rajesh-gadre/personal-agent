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


# ── Entry points ──


def _watch_dirs() -> list[Path]:
    """Return all directories to watch: ~/Receipts + data/incoming."""
    dirs = [Path(settings.receipt_watch_folder).expanduser()]
    incoming = Path(settings.receipt_incoming_folder)
    if incoming not in dirs:
        dirs.append(incoming)
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def run_watcher() -> None:
    """Run watcher as a blocking main process. Use for standalone execution."""
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    watch_dirs = _watch_dirs()
    mode = getattr(settings, "receipt_watcher_mode", "event")

    # Process files already in folders
    for d in watch_dirs:
        logger.info(f"Watcher: scanning existing files in {d}")
        _scan_existing(d)

    if mode == "event":
        observers = []
        for d in watch_dirs:
            logger.info(f"Watcher: monitoring {d} (event mode)")
            obs = _create_event_observer(d)
            obs.start()
            observers.append(obs)

        def _shutdown(signum, frame):
            logger.info("Watcher: shutting down...")
            for obs in observers:
                obs.stop()
                obs.join()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            for obs in observers:
                obs.join()
        except KeyboardInterrupt:
            for obs in observers:
                obs.stop()
                obs.join()
    else:
        # Poll mode: scan all folders in one loop
        interval = settings.receipt_watch_interval_seconds
        logger.info(f"Watcher: polling {[str(d) for d in watch_dirs]} every {interval}s")
        while True:
            for d in watch_dirs:
                try:
                    _scan_existing(d)
                except Exception as e:
                    logger.error(f"Watcher: error polling {d}: {e}")
            time.sleep(interval)


_watcher_thread: threading.Thread | None = None


def start_watcher() -> None:
    """Start the watcher in a background thread (for use inside Streamlit)."""
    global _watcher_thread
    if _watcher_thread is not None and _watcher_thread.is_alive():
        return

    watch_dirs = _watch_dirs()
    mode = getattr(settings, "receipt_watcher_mode", "event")

    for d in watch_dirs:
        _scan_existing(d)

    if mode == "event":
        # Start one observer per folder; keep reference to first as _watcher_thread
        observers = []
        for d in watch_dirs:
            obs = _create_event_observer(d)
            obs.daemon = True
            obs.start()
            observers.append(obs)
            logger.info(f"Watcher: background event watcher started on {d}")
        _watcher_thread = observers[0]
    else:
        def _poll_all():
            interval = settings.receipt_watch_interval_seconds
            while True:
                for d in watch_dirs:
                    try:
                        _scan_existing(d)
                    except Exception as e:
                        logger.error(f"Watcher: error polling {d}: {e}")
                time.sleep(interval)

        _watcher_thread = threading.Thread(target=_poll_all, daemon=True, name="receipt-watcher")
        _watcher_thread.start()
        logger.info(f"Watcher: background poll watcher started on {[str(d) for d in watch_dirs]}")


if __name__ == "__main__":
    run_watcher()
