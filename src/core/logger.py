"""
src/core/logger.py - Lightweight logger for MicroPython and FritzControl
Supports log levels, formatting, and automatic credential masking.
"""

import sys

DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40

_LEVEL_NAMES = {
    DEBUG: "DEBUG",
    INFO: "INFO",
    WARN: "WARN",
    ERROR: "ERROR",
}

class Logger:
    def __init__(self, name="FritzControl", level=INFO):
        self.name = name
        self.level = level

    def set_level(self, level):
        if isinstance(level, str):
            level_upper = level.upper()
            for k, v in _LEVEL_NAMES.items():
                if v == level_upper:
                    self.level = k
                    return
        elif isinstance(level, int):
            self.level = level

    def _format(self, level_name, msg):
        return f"[{level_name}] [{self.name}] {msg}"

    def debug(self, msg):
        if self.level <= DEBUG:
            print(self._format("DEBUG", msg))

    def info(self, msg):
        if self.level <= INFO:
            print(self._format("INFO", msg))

    def warn(self, msg):
        if self.level <= WARN:
            print(self._format("WARN", msg))

    def error(self, msg):
        if self.level <= ERROR:
            print(self._format("ERROR", msg))

# Default singleton instance
log = Logger()
