import datetime
import logging
import os
from typing import Optional

from utils.path_sandbox import safe_path


LOG_ROOT = safe_path("logs")
os.makedirs(LOG_ROOT, exist_ok=True)

DEFAULT_LOG_FORMAT = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
LOG_INTERVAL_MINUTES = 5


def get_interval_log_file(name: str, log_time=None, interval_minutes: int = LOG_INTERVAL_MINUTES) -> str:
    log_time = log_time or datetime.datetime.now()
    interval_minute = (log_time.minute // interval_minutes) * interval_minutes
    interval_time = log_time.replace(minute=interval_minute, second=0, microsecond=0)
    return os.path.join(LOG_ROOT, f"{name}_{interval_time.strftime('%Y-%m-%d_%H-%M')}.log")


class IntervalFileHandler(logging.FileHandler):
    """按固定时间窗口切分日志，避免测试时单个日志文件无限增长。"""

    def __init__(self, name: str, interval_minutes: int = LOG_INTERVAL_MINUTES, encoding: str = "utf-8"):
        self.name_prefix = name
        self.interval_minutes = interval_minutes
        self.current_interval = self._get_interval(datetime.datetime.now())
        super().__init__(
            get_interval_log_file(self.name_prefix, self.current_interval, self.interval_minutes),
            encoding=encoding,
        )

    def _get_interval(self, log_time):
        interval_minute = (log_time.minute // self.interval_minutes) * self.interval_minutes
        return log_time.replace(minute=interval_minute, second=0, microsecond=0)

    def _switch_file_if_needed(self, record) -> None:
        record_time = datetime.datetime.fromtimestamp(record.created)
        record_interval = self._get_interval(record_time)
        if record_interval == self.current_interval:
            return

        self.current_interval = record_interval
        if self.stream:
            self.stream.flush()
            self.stream.close()
            self.stream = None

        self.baseFilename = os.path.abspath(
            get_interval_log_file(self.name_prefix, self.current_interval, self.interval_minutes)
        )
        self.stream = self._open()

    def emit(self, record) -> None:
        self.acquire()
        try:
            self._switch_file_if_needed(record)
            super().emit(record)
        finally:
            self.release()


def get_logger(
    name: str = "agent",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_file: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        file_handler = IntervalFileHandler(name, interval_minutes=LOG_INTERVAL_MINUTES, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger


logger = get_logger()
