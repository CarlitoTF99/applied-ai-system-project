"""Logging for the VibeMatch agent: always to logs/agent.log, optionally to the console."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from src.config import LOG_DIR, LOG_FILE

LOGGER_NAME = "vibematch"
FORMAT = "%(asctime)s | %(levelname)s | run=%(run_id)s | step=%(step)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _ContextFilter(logging.Filter):
    """Fill run_id and step with "-" when a log call doesn't pass them, so the format never fails."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "-"
        if not hasattr(record, "step"):
            record.step = "-"
        return True


def configure(verbose: bool = False) -> logging.Logger:
    """Set up the vibematch logger (idempotent) and return it."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(FORMAT, DATE_FORMAT)
    context = _ContextFilter()

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context)
        logger.addHandler(file_handler)
    except OSError as exc:
        # A read-only folder shouldn't stop recommendations from working
        print(f"warning: could not open {LOG_FILE}: {exc}", file=sys.stderr)

    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("[%(levelname)s] %(step)s: %(message)s"))
        console.addFilter(context)
        logger.addHandler(console)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


class StepLogger(logging.LoggerAdapter):
    """A logger bound to one run_id; pass step= on each call."""

    def process(self, msg, kwargs):
        step = kwargs.pop("step", "-")
        kwargs["extra"] = {"run_id": self.extra["run_id"], "step": step}
        return msg, kwargs


def get_run_logger(run_id: str) -> StepLogger:
    """Return a StepLogger that tags every line with run_id."""
    return StepLogger(logging.getLogger(LOGGER_NAME), {"run_id": run_id})
