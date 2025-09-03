import os
import json
import aiohttp
import discord
import datetime
from dotenv import load_dotenv
import feedparser
from discord.ext import commands, tasks
from typing import Any, Dict, List, Optional, Tuple

from extensions.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)

API_BASE = "https://animeschedule.net/api/v3/"
TIMETABLE_ENDPOINT = API_BASE + "timetables"

CONFIG_PATH = "scheduleConfig.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "channel_id": [],
    "post_time": "01:00",
    "api_key": os.getenv("SCHEDULE"),
    # RSS related
    "rss_enabled": False,
    "rss_url": "https://animeschedule.net/subrss.xml",
    "rss_interval_minutes": 5,
    "rss_channel_id": [],  # fallback to channel_id if empty
    "rss_post_limit": 5,
    "rss_seen_guids": [],
}


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)

            if not isinstance(data.get("channel_id", []), list):
                data["channel_id"] = []

            return data
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except Exception:
        logger.exception("Failed Loading Schedule Config - Using Defaults")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Schedule Config")


def _parse_iso_datetime(s: str) -> Optional[datetime.datetime]:
    if not s:
        return None

    try:
        s = s.strip()

        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        dt = datetime.datetime.fromisoformat(s)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)

        return dt
    except Exception:
        fmts = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in fmts:
            try:
                dt = datetime.datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                else:
                    dt = dt.astimezone(datetime.timezone.utc)
                return dt
            except Exception:
                continue
    return None


def _get_field(obj: Dict[str, Any], *names: str, default=None):
    # Case-insensitive lookup across multiple alias names
    if not isinstance(obj, dict):
        return default

    # Direct matches first
    for n in names:
        if n in obj:
            return obj[n]

    # Build a lowercase key map once
    try:
        lower_map = {str(k).lower(): v for k, v in obj.items()}
    except Exception:
        lower_map = {}

    for n in names:
        v = lower_map.get(str(n).lower())
        if v is not None:
            return v

    return default


def _weekday_name(weekday_int: int) -> str:
    days = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]
    try:
        return days[int(weekday_int) % 7]
    except Exception:
        return "Unknown"


class Schedule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self._last_post_date: Optional[datetime.date] = None
        self.auto_task.start()
        # RSS runtime cache
        self._rss_seen = set(self.config.get("rss_seen_guids", []) or [])
        # Apply configured interval and start RSS polling
        try:
            interval_min = max(1, int(self.config.get("rss_interval_minutes", 5) or 5))
        except Exception:
            interval_min = 5
        self.rss_task.change_interval(minutes=interval_min)
        self.rss_task.start()

    def cog_unload(self):
        self.auto_task.cancel()
        self.rss_task.cancel()

    async def fetch_timetable(self) -> Optional[List[Dict[str, Any]]]:
        headers = {"User-Agent": "AstrumOtaku"}
        api_key = self.config.get("api_key") or ""

        if api_key:
            # Support both common auth header styles
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-Key"] = api_key

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(TIMETABLE_ENDPOINT, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("AnimeSchedule Returned %s", resp.status)
                        raise RuntimeError(f"HTTP {resp.status}")

                    data = await resp.json()
                    if isinstance(data, list):
                        return data

                    if isinstance(data, dict):
                        for k in ("timetables", "data", "results"):
                            if k in data and isinstance(data[k], list):
                                return data[k]

                    return None
        except Exception:
            logger.exception("Failed To Fetch Timetables")
            # Fallback to local snapshot if available
            try:
                with open("schedule.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    logger.info("Using local schedule.json fallback")
                    return data
            except Exception:
                pass
            return None

    def _format_show_line(
        self, anime: Dict[str, Any], dt: Optional[datetime.datetime] = None
    ) -> Tuple[str, str, str]:
        title = _get_field(anime, "title", "Title", "name", default="Unknown")

        episode_number = _get_field(
            anime, "episode_number", "episodeNumber", default=None
        )
        episodes_total = _get_field(anime, "episodes", "Episodes", default=None)

        ep_str = f"Ep {episode_number}" if episode_number is not None else "Ep ?"
        try:
            if (
                episodes_total is not None
                and episode_number is not None
                and int(episodes_total) == int(episode_number)
            ):
                ep_str = f"Ep {episode_number}F"
        except Exception:
            pass

        if not dt:
            episode_date_raw = _get_field(
                anime, "episode_date", "episodeDate", "EpisodeDate", default=None
            )
            if episode_date_raw:
                dt = _parse_iso_datetime(str(episode_date_raw))

        time_str = dt.strftime("%H:%M") if dt else "Unknown"

        return title, ep_str, time_str

    async def build_day_schedule_message(self, weekday: int) -> str:
        data = await self.fetch_timetable()

        if not data:
            return "Could Not Fetch Schedule Right Now!"

        air_rank = {"sub": 3, "dub": 2, "raw": 1}
        best_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for a in data:
            route = _get_field(a, "route", "Route", default="")
            if not route:
                continue

            media_types = _get_field(a, "mediaTypes", "media_types", default=[]) or []
            is_ona_chinese = False

            for m in media_types:
                if not isinstance(m, dict):
                    continue

                mroute = _get_field(m, "route", "Route", default="").lower()
                mname = _get_field(m, "name", "Name", default="").lower()

                if mroute == "ona-chinese" or mname == "ona (chinese)":
                    is_ona_chinese = True
                    break

            if is_ona_chinese:
                continue

            episode_date_raw = _get_field(
                a, "episode_date", "episodeDate", "EpisodeDate", default=None
            )
            dt = (
                _parse_iso_datetime(str(episode_date_raw)) if episode_date_raw else None
            )
            if dt is None:
                continue

            day_key = (dt.weekday() + 1) % 7
            key = (route, day_key)

            air_type = _get_field(a, "air_type", "airType", default="").lower()
            rank = air_rank.get(air_type, 0)

            cur_best = best_by_key.get(key)
            if cur_best is None:
                best_by_key[key] = a
            else:
                cur_rank = air_rank.get(
                    _get_field(cur_best, "air_type", "airType", default="").lower(), 0
                )
                if rank > cur_rank:
                    best_by_key[key] = a

                elif rank == cur_rank:

                    def _dt(x):
                        raw = _get_field(
                            x,
                            "episode_date",
                            "episodeDate",
                            "EpisodeDate",
                            default=None,
                        )
                        return _parse_iso_datetime(str(raw)) if raw else None

                    old_dt = _dt(cur_best)
                    new_dt = _dt(a)

                    if (old_dt is None and new_dt is not None) or (
                        old_dt is not None and new_dt is not None and new_dt > old_dt
                    ):
                        best_by_key[key] = a

        shows: List[Tuple[str, str, Optional[datetime.datetime]]] = []
        for (route, day_key), a in best_by_key.items():
            if day_key != weekday:
                continue
            episode_date_raw = _get_field(
                a, "episode_date", "episodeDate", "EpisodeDate", default=None
            )
            dt = (
                _parse_iso_datetime(str(episode_date_raw)) if episode_date_raw else None
            )
            if dt is None:
                continue
            title, ep_str, _ = self._format_show_line(a, dt)
            shows.append((title, ep_str, dt))

        shows.sort(
            key=lambda x: (
                x[2] or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
                x[0].lower(),
            )
        )

        lines: List[str] = [f"**__{_weekday_name(weekday)} Schedule :__**\n"]

        if not shows:
            lines.append("_No Shows Found For The Day!_")
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            next_idx = None

            for i, (_, _, dt) in enumerate(shows):
                if dt and dt >= now:
                    next_idx = i
                    break

            for i, (title, ep_str, dt) in enumerate(shows):
                if dt is not None:
                    ts = int(dt.timestamp())
                    time_token = f"<t:{ts}:t>"
                else:
                    time_token = "Unknown"

                prefix = "➡️ " if i == (next_idx or -1) else ""
                lines.append(f"{prefix}{title} - {ep_str} - {time_token}")

        lines.append("\n**Full Week:** <https://AnimeSchedule.net>")
        return "\n".join(lines)

    # --- RSS polling ---
    def _parse_rfc822(self, s: str) -> Optional[datetime.datetime]:
        if not s:
            return None
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(s)
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            else:
                dt = dt.astimezone(datetime.timezone.utc)
            return dt
        except Exception:
            return None

    async def _fetch_rss(self) -> Optional[bytes]:
        url = str(self.config.get("rss_url") or "https://animeschedule.net/subrss.xml")
        headers = {"User-Agent": "AstrumOtaku RSS"}
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("RSS Returned %s", resp.status)
                        return None
                    return await resp.read()
        except Exception:
            logger.exception("Failed Fetching RSS")
            return None

    def _format_rss_message(self, entry: dict) -> str:
        title = entry.get("title") or "New episode"
        link = entry.get("link") or "https://AnimeSchedule.net"
        pub = entry.get("published") or entry.get("pubDate") or ""
        dt = self._parse_rfc822(pub)
        when = f" <t:{int(dt.timestamp())}:t>" if dt else ""
        return f"[SUB] {title}{when}\n{link}"

    def _persist_rss_seen(self):
        try:
            # Keep last N guids to cap file growth
            max_keep = 500
            self.config["rss_seen_guids"] = list(self._rss_seen)[-max_keep:]
            save_config(self.config)
        except Exception:
            logger.exception("Failed to persist RSS seen GUIDs")

    @tasks.loop(minutes=5.0)
    async def rss_task(self):
        try:
            if not (self.config.get("rss_enabled") or self.config.get("enabled")):
                return

            raw = await self._fetch_rss()
            if not raw:
                return

            parsed = feedparser.parse(raw)
            entries = parsed.get("entries", []) if isinstance(parsed, dict) else []
            if not entries:
                return

            # Identify new entries by GUID (fallback to link+title)
            new_items = []
            for e in entries:
                guid = (
                    e.get("guid")
                    or e.get("id")
                    or f"{e.get('link', '')}|{e.get('title', '')}"
                )
                if guid not in self._rss_seen:
                    new_items.append((guid, e))

            if not new_items:
                return

            # Oldest first to maintain order; use published date when available
            def _dt(e):
                return self._parse_rfc822(
                    e.get("published") or e.get("pubDate") or ""
                ) or datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)

            new_items.sort(key=lambda ge: _dt(ge[1]))

            # Limit per cycle
            limit = max(1, int(self.config.get("rss_post_limit", 5) or 5))
            to_post = new_items[:limit]

            # Determine channels
            channels = (
                self.config.get("rss_channel_id") or self.config.get("channel_id") or []
            )
            if not channels:
                logger.info("RSS enabled but no channels configured")

            # Post
            for guid, e in to_post:
                msg = self._format_rss_message(e)
                for cid in channels:
                    try:
                        cid_int = int(cid) if not isinstance(cid, int) else cid
                        channel = self.bot.get_channel(
                            cid_int
                        ) or await self.bot.fetch_channel(cid_int)
                        if channel:
                            await channel.send(msg)
                    except Exception:
                        logger.exception("Failed posting RSS to channel %s", cid)

                self._rss_seen.add(guid)

            # Persist seen list after posting batch
            self._persist_rss_seen()
        except Exception:
            logger.exception("Error in RSS task loop")

    @rss_task.before_loop
    async def before_rss_task(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=30.0)
    async def auto_task(self):
        try:
            if not self.config.get("enabled", False):
                return

            post_time = str(self.config.get("post_time", "01:00"))
            try:
                hour, minute = [int(x) for x in post_time.split(":")]

            except Exception:
                hour, minute = 1, 0

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today_date = now_utc.date()

            if self._last_post_date == today_date:
                return

            if now_utc.hour == hour and now_utc.minute == minute:
                py_weekday = now_utc.weekday()  # Mon=0..Sun=6
                sunday_based = (py_weekday + 1) % 7

                message = await self.build_day_schedule_message(sunday_based)

                channel_ids = self.config.get("channel_id", []) or []
                if not channel_ids:
                    logger.info("Schedule Auto Post Enabled But No Channel Configured!")

                for cid in channel_ids:
                    try:
                        if isinstance(cid, str) and cid.isdigit():
                            cid = int(cid)

                        channel = self.bot.get_channel(int(cid))

                        if channel is None:
                            channel = await self.bot.fetch_channel(int(cid))

                        if channel is None:
                            logger.warning(
                                "Could Not Find Channel %s To Post Schedule", cid
                            )
                            continue
                        await channel.send(message)
                        logger.info("Posted Daily Schedule To %s", cid)

                    except Exception:
                        logger.exception("Failed To Post Schedule To Channel %s", cid)

                self._last_post_date = today_date

        except Exception:
            logger.exception("Error In Schedule Auto Task")

    @auto_task.before_loop
    async def before_auto_task(self):
        await self.bot.wait_until_ready()

    @discord.slash_command(name="schedule", description="Test")
    async def schedule_command(
        self, ctx: discord.ApplicationContext, day: Optional[str] = None
    ):
        target = None
        if not day:
            py_weekday = datetime.datetime.now(datetime.timezone.utc).weekday()
            target = (py_weekday + 1) % 7
        else:
            d = day.strip().lower()
            mapping = {
                "sun": 0,
                "sunday": 0,
                "mon": 1,
                "monday": 1,
                "tue": 2,
                "tues": 2,
                "tuesday": 2,
                "wed": 3,
                "wednesday": 3,
                "thu": 4,
                "thur": 4,
                "thurs": 4,
                "thursday": 4,
                "fri": 5,
                "friday": 5,
                "sat": 6,
                "saturday": 6,
            }
            if d.isdigit():
                v = int(d)
                if 0 <= v <= 6:
                    target = v
                else:
                    await ctx.respond(
                        "Please Provide A Day Between 0 ( Sunday ) And 6 ( Saturday )."
                    )
                    return
            elif d in mapping:
                target = mapping[d]
            else:
                await ctx.respond(
                    "Unknown Day. Please Use Names Like Monday Or Numbers 0..6 ( Sunday = 0 )."
                )
                return

        msg = await self.build_day_schedule_message(target)

        if len(msg) > 2000:
            parts = []
            current = []
            cur_len = 0

            for line in msg.splitlines(keepends=True):
                if cur_len + len(line) > 1900:
                    parts.append("".join(current))
                    current = [line]
                    cur_len = len(line)

                else:
                    current.append(line)
                    cur_len += len(line)

            if current:
                parts.append("".join(current))

            for p in parts:
                await ctx.respond(p)
        else:
            await ctx.respond(msg)


def setup(bot: commands.Bot):
    logger.info("Loaded : Schedule Cog")
    bot.add_cog(Schedule(bot))
