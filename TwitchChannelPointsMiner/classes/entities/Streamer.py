import logging
import time
from threading import Lock

from TwitchChannelPointsMiner.classes.Chat import ChatPresence, ThreadChat
from TwitchChannelPointsMiner.classes.entities.Stream import Stream
from TwitchChannelPointsMiner.classes.Settings import Events, Settings
from TwitchChannelPointsMiner.constants import URL
from TwitchChannelPointsMiner.utils import _millify

logger = logging.getLogger(__name__)


class StreamerSettings(object):
    __slots__ = [
        "follow_raid",
        "watch_streak",
        "chat",
    ]

    def __init__(
        self,
        follow_raid: bool = None,
        watch_streak: bool = None,
        chat: ChatPresence = None,
    ):
        self.follow_raid = follow_raid
        self.watch_streak = watch_streak
        self.chat = chat

    def default(self):
        for name in [
            "follow_raid",
            "watch_streak",
        ]:
            if getattr(self, name) is None:
                setattr(self, name, True)
        if self.chat is None:
            self.chat = ChatPresence.ONLINE

    def __repr__(self):
        return f"follow_raid={self.follow_raid}, watch_streak={self.watch_streak}, chat={self.chat})"


class Streamer(object):
    __slots__ = [
        "username",
        "channel_id",
        "settings",
        "is_online",
        "stream_up",
        "online_at",
        "offline_at",
        "channel_points",
        "minute_watched_requests",
        "viewer_is_mod",
        "activeMultipliers",
        "irc_chat",
        "stream",
        "raid",
        "history",
        "streamer_url",
        "mutex",
    ]

    def __init__(self, username, settings=None):
        self.username: str = username.lower().strip()
        self.channel_id: str = ""
        self.settings = settings
        self.is_online = False
        self.stream_up = 0
        self.online_at = 0
        self.offline_at = 0
        self.channel_points = 0
        self.minute_watched_requests = None
        self.viewer_is_mod = False
        self.activeMultipliers = None
        self.irc_chat = None

        self.stream = Stream()

        self.raid = None
        self.history = {}

        self.streamer_url = f"{URL}/{self.username}"

        self.mutex = Lock()

    def __repr__(self):
        return f"Streamer(username={self.username}, channel_id={self.channel_id}, channel_points={_millify(self.channel_points)})"

    def __str__(self):
        return (
            f"{self.username} ({_millify(self.channel_points)} points)"
            if Settings.logger.less
            else self.__repr__()
        )

    def set_offline(self):
        if self.is_online is True:
            self.offline_at = time.time()
            self.is_online = False

        self.toggle_chat()

        logger.info(
            f"{self} is Offline!",
            extra={
                "emoji": ":sleeping:",
                "event": Events.STREAMER_OFFLINE,
            },
        )

    def set_online(self):
        if self.is_online is False:
            self.online_at = time.time()
            self.is_online = True
            self.stream.init_watch_streak()

        self.toggle_chat()

        logger.info(
            f"{self} is Online!",
            extra={
                "emoji": ":partying_face:",
                "event": Events.STREAMER_ONLINE,
            },
        )

    def print_history(self):
        return ", ".join(
            [
                f"{key}({self.history[key]['counter']} times, {_millify(self.history[key]['amount'])} gained)"
                for key in sorted(self.history)
                if self.history[key]["counter"] != 0
            ]
        )

    def update_history(self, reason_code, earned, counter=1):
        if reason_code not in self.history:
            self.history[reason_code] = {"counter": 0, "amount": 0}
        self.history[reason_code]["counter"] += counter
        self.history[reason_code]["amount"] += earned

        if reason_code == "WATCH_STREAK":
            self.stream.watch_streak_missing = False

    def stream_up_elapsed(self):
        return self.stream_up == 0 or ((time.time() - self.stream_up) > 120)

    def viewer_has_points_multiplier(self):
        return self.activeMultipliers is not None and len(self.activeMultipliers) > 0

    def total_points_multiplier(self):
        return (
            sum(
                map(
                    lambda x: x["factor"],
                    self.activeMultipliers,
                ),
            )
            if self.activeMultipliers is not None
            else 0
        )

    def leave_chat(self):
        if self.irc_chat is not None:
            self.irc_chat.stop()

            # Recreate a new thread to start again
            # raise RuntimeError("threads can only be started once")
            self.irc_chat = ThreadChat(
                self.irc_chat.username,
                self.irc_chat.token,
                self.username,
            )

    def __join_chat(self):
        if self.irc_chat is not None:
            if self.irc_chat.is_alive() is False:
                self.irc_chat.start()

    def toggle_chat(self):
        if self.settings.chat == ChatPresence.ALWAYS:
            self.__join_chat()
        elif self.settings.chat != ChatPresence.NEVER:
            if self.is_online is True:
                if self.settings.chat == ChatPresence.ONLINE:
                    self.__join_chat()
                elif self.settings.chat == ChatPresence.OFFLINE:
                    self.leave_chat()
            else:
                if self.settings.chat == ChatPresence.ONLINE:
                    self.leave_chat()
                elif self.settings.chat == ChatPresence.OFFLINE:
                    self.__join_chat()
