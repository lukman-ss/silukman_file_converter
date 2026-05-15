import logging
import logging.handlers
import threading
from pathlib import Path

_lock = threading.Lock()
_loggers: dict[str, logging.Logger] = {}

# Rotate at 5 MB, keep 3 backups
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def get_logger(name: str = "silukman_file_converter") -> logging.Logger:
    with _lock:
        if name in _loggers:
            return _loggers[name]

        logger = logging.getLogger(name)
        if logger.handlers:
            _loggers[name] = logger
            return logger

        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s - %(message)s")

        # Try to set up a rotating file handler; fall back to stderr if the
        # log directory cannot be created (e.g. read-only filesystem).
        try:
            log_dir = Path("output") / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "app.log"
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            # Cannot write to disk — log to stderr only
            pass

        # Always add a stderr handler so errors are visible even without a log file
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        _loggers[name] = logger
        return logger
