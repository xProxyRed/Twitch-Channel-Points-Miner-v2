import logging
import os
import platform
import queue
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from pathlib import Path

import emoji
# from colorama import Fore, init

from TwitchChannelPointsMiner.classes.Settings import Events
from TwitchChannelPointsMiner.utils import remove_emoji


class LoggerSettings:
    __slots__ = [
        "save",
        "less",
        "console_level",
        "console_username",
        "file_level",
        "emoji",
        "colored",
        "auto_clear",
    ]

    def __init__(
        self,
        save: bool = True,
        less: bool = False,
        console_level: int = logging.INFO,
        console_username: bool = False,
        file_level: int = logging.DEBUG,
        emoji: bool = platform.system() != "Windows",
        colored: bool = False,
        auto_clear: bool = True,
    ):
        self.save = save
        self.less = less
        self.console_level = console_level
        self.console_username = console_username
        self.file_level = file_level
        self.emoji = emoji
        self.colored = colored
        # self.color_palette = color_palette
        self.auto_clear = auto_clear


class GlobalFormatter(logging.Formatter):
    def __init__(self, *, fmt, settings: LoggerSettings, datefmt=None):
        self.settings = settings
        logging.Formatter.__init__(self, fmt=fmt, datefmt=datefmt)

    def format(self, record):
        record.emoji_is_present = (
            record.emoji_is_present if hasattr(
                record, "emoji_is_present") else False
        )
        if (
            hasattr(record, "emoji")
            and self.settings.emoji is True
            and record.emoji_is_present is False
        ):
            record.msg = emoji.emojize(
                f"{record.emoji}  {record.msg.strip()}", language="alias"
            )
            record.emoji_is_present = True

        if self.settings.emoji is False:
            if "\u2192" in record.msg:
                record.msg = record.msg.replace("\u2192", "-->")

            # With the update of Stream class, the Stream Title may contain emoji
            # Full remove using a method from utils.
            record.msg = remove_emoji(record.msg)

        if hasattr(record, "event"):
            if self.settings.colored is True:
                record.msg = (
                    f"{self.settings.color_palette.get(record.event)}{record.msg}"
                )

        return super().format(record)


def configure_loggers(username, settings):
    # Queue handler that will handle the logger queue
    logger_queue = queue.Queue(-1)
    queue_handler = QueueHandler(logger_queue)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Add the queue handler to the root logger
    # Send log messages to another thread through the queue
    root_logger.addHandler(queue_handler)

    # Adding a username to the format based on settings
    console_username = "" if settings.console_username is False else f"[{username}] "

    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.console_level)
    console_handler.setFormatter(
        GlobalFormatter(
            fmt=(
                "%(asctime)s - %(levelname)s - [%(funcName)s]: " +
                console_username + "%(message)s"
                if settings.less is False
                else "%(asctime)s - " + console_username + "%(message)s"
            ),
            datefmt=(
                "%d/%m/%y %H:%M:%S" if settings.less is False else "%d/%m %H:%M:%S"
            ),
            settings=settings,
        )
    )

    if settings.save is True:
        logs_path = os.path.join(Path().absolute(), "logs")
        Path(logs_path).mkdir(parents=True, exist_ok=True)
        if settings.auto_clear is True:
            logs_file = os.path.join(
                logs_path,
                f"{username}.log",
            )
            file_handler = TimedRotatingFileHandler(
                logs_file,
                when="D",
                interval=1,
                backupCount=7,
                encoding="utf-8",
                delay=False,
            )
        else:
            logs_file = os.path.join(
                logs_path,
                f"{username}.{datetime.now().strftime('%Y%m%d-%H%M%S')}.log",
            )
            file_handler = logging.FileHandler(logs_file, "w", "utf-8")

        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s]: %(message)s",
                datefmt="%d/%m/%y %H:%M:%S",
            )
        )
        file_handler.setLevel(settings.file_level)

        # Add logger handlers to the logger queue and start the process
        queue_listener = QueueListener(
            logger_queue, file_handler, console_handler, respect_handler_level=True
        )
        queue_listener.start()
        return logs_file, queue_listener
    else:
        queue_listener = QueueListener(
            logger_queue, console_handler, respect_handler_level=True
        )
        queue_listener.start()
        return None, queue_listener
