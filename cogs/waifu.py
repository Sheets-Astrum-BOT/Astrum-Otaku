import json
import time
import random
import discord
import aiohttp
import asyncio
import datetime
from discord import option
from discord.ext import commands
from extensions.logger import setup_logger
from extensions.database import database

logger = setup_logger(__name__)

WAIFU_CATEGORIES = [
    "maid",
    "waifu",
    "marin-kitagawa",
    "mori-calliope",
    "raiden-shogun",
    "oppai",
    "selfies",
    "uniform",
    "kamisato-ayaka",
]
NWAIFU_CATEGORIES = ["ass", "hentai", "milf", "oral", "paizuri", "ecchi", "ero"]

API_URL = "https://api.waifu.im/search"

CONFIG_PATH = "waifuConfig.json"
NSFW_CHANCE = 0.005

DEFAULT_CONFIG = {
    "enabled": True,
    "channel_id": [1401985460808712293],
    "interval_minutes": 60,
    "only_spawner": False,
    "owner_id": [727012870683885578],
}


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)

            return data
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    except Exception:
        logger.exception("Failed Loading Waifu Config - Using Defaults")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Waifu Config")


class Waifu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        try:
            self.db = database("astrumotaku.db")
        except Exception:
            logger.exception("Failed To Initialize Database")
            self.db = None

        self.claim_cooldown = 60 * 60

        self._spawn_task = bot.loop.create_task(self._auto_spawn_loop())

    def cog_unload(self):
        try:
            self._spawn_task.cancel()
        except Exception:
            pass

    async def _auto_spawn_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                cfg = load_config()
                if cfg.get("enabled") and cfg.get("channel_id"):

                    ch_ids = cfg.get("channel_id")
                    if not isinstance(ch_ids, list):
                        ch_ids = [ch_ids]

                    for ch in ch_ids:
                        try:
                            ch_id = int(ch)
                        except Exception:
                            continue

                        channel = self.bot.get_channel(ch_id)
                        if not channel:
                            logger.warning("Configured Waifu Channel Not Found - Disabling")

                        do_nsfw = random.random() < NSFW_CHANCE
                        tag_list = NWAIFU_CATEGORIES if do_nsfw else WAIFU_CATEGORIES
                        tag = random.choice(tag_list) if tag_list else "waifu"

                        image = await self.fetch_waifu([tag], nsfw=do_nsfw)
                        if not image:
                            continue

                        try:
                            if self.db:
                                waifu_api_id = image.get("image_id") or image.get(
                                    "signature"
                                )
                                artist = image.get("artist") or {}
                                tags = [t.get("name") for t in image.get("tags", [])]

                                self.db.add_waifu(
                                    waifu_api_id,
                                    image.get("url"),
                                    image.get("preview_url"),
                                    image.get("source"),
                                    (
                                        artist.get("name")
                                        if isinstance(artist, dict)
                                        else None
                                    ),
                                    (
                                        artist.get("twitter")
                                        if isinstance(artist, dict)
                                        else None
                                    ),
                                    bool(image.get("is_nsfw", False)),
                                    json.dumps(tags),
                                )

                                waifu_row = self.db.get_waifu_by_api_id(waifu_api_id)
                                waifu_db_id = waifu_row[0] if waifu_row else None
                            else:
                                waifu_db_id = None
                        except Exception:
                            logger.exception("Failed Saving Waifu To Database")
                            waifu_db_id = None

                        embed = discord.Embed(
                            title=f"✨ Spawned Waifu ~ {tag}",
                            color=discord.Color.random(),
                        )
                        embed.set_image(url=image.get("url"))
                        artist = image.get("artist") or {}

                        if artist:
                            embed.add_field(
                                name="Artist",
                                value=artist.get("name") or "Unknown",
                                inline=True,
                            )

                        view = ClaimView(self, waifu_db_id)

                        try:
                            await channel.send(embed=embed, view=view)
                            logger.info(f"Auto Posted Waifu To {channel.id}")
                        except Exception:
                            logger.exception("Failed Sending Waifu To %s", channel)

                        try:
                            await asyncio.sleep(random.uniform(0.5, 2.0))
                        except Exception:
                            pass

                interval = (
                    cfg.get("interval_minutes", 60) if isinstance(cfg, dict) else 60
                )
                await asyncio.sleep(max(30, interval * 60))

            except asyncio.CancelledError:
                break

            except Exception:
                logger.exception("Error In Auto Spawn")
                await asyncio.sleep(60)

    def _format_last_claim(self, last_row):
        if not last_row:
            return "Never"

        ts = last_row[0]

        if not ts:
            return "Never"

        try:
            if isinstance(ts, str):
                return ts

            return str(ts)
        except Exception:
            return str(ts)

    @discord.slash_command(name="profile", description="Show Your Waifu Profile")
    async def profile_cmd(
        self, ctx: discord.ApplicationContext, member: discord.Member = None
    ):
        member = member or ctx.author
        if not self.db:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Error",
                    description="Database Unavailable.",
                    color=discord.Color.red(),
                )
            )

        row = self.db.get_user(member.id)
        if not row:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Profile",
                    description=f"{member.display_name} Has No Waifus Yet!",
                    color=discord.Color.blue(),
                )
            )

        username = row[2]
        waifu_count = row[3]
        last_claim = self._format_last_claim(row[4:5])

        embed = discord.Embed(
            title=f"{member.display_name}'s Profile", color=discord.Color.random()
        )
        embed.add_field(name="Username", value=username, inline=False)
        embed.add_field(name="Total Waifus", value=str(waifu_count), inline=False)
        embed.add_field(name="Last Claim", value=last_claim, inline=False)

        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await ctx.respond(embed=embed)

    @discord.slash_command(name="collection", description="Show Your Waifu Collection")
    async def collection_cmd(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member = None,
        tag: str = None,
    ):
        member = member or ctx.author
        if not self.db:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Error",
                    description="Database Unavailable.",
                    color=discord.Color.red(),
                )
            )

        user_row = self.db.get_user(member.id)
        if not user_row:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Collection",
                    description=f"{member.display_name} Has No Waifus Yet!",
                    color=discord.Color.blue(),
                )
            )

        waifus = self.db.get_user_collection(user_row[0])

        if tag:
            waifus = [w for w in waifus if tag in (w[8] or "")]

        if not waifus:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Collection",
                    description="No Waifus Found",
                    color=discord.Color.blue(),
                )
            )

        pages = []
        for w in waifus:
            embed = discord.Embed(title=f"Waifu {w[0]}", color=discord.Color.random())

            embed.set_image(url=w[2])

            embed.add_field(name="Artist", value=w[5] or "Unknown", inline=True)
            embed.add_field(
                name="Source", value=f"[Link]({w[4]})" or "Unknown", inline=True
            )

            if w[7] == 1:
                embed.add_field(name="NSFW", value=str(bool(w[7])), inline=False)

            embed.add_field(
                name="Tags",
                value=", ".join(map(str, w[8])) if w[8] else "",
                inline=True,
            )
            pages.append(embed)

        view = PagesView(pages, ctx.author.id)
        await ctx.respond(embed=pages[0], view=view)

    @discord.slash_command(name="leaderboard", description="Top Waifu Collectors")
    async def leaderboard_cmd(self, ctx: discord.ApplicationContext):
        if not self.db:
            return await ctx.respond(
                embed=discord.Embed(
                    title="Error",
                    description="Database Unavailable.",
                    color=discord.Color.red(),
                )
            )

        rows = self.db.get_leaderboard(10)
        embed = discord.Embed(title="💖 Waifu Leaderboard ~", color=discord.Color.gold())

        text = ""

        for i, r in enumerate(rows, start=1):
            text += f"{i}. {r[0]} — {r[1]}\n"

        embed.description = text or "No Data!"
        await ctx.respond(embed=embed)

    async def fetch_waifu(self, tags, nsfw=False):
        params = {
            "included_tags": tags,
            "is_nsfw": "true" if nsfw else "false",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"API Request Failed : {resp.status}")
                        logger.error(f"Response : {await resp.text()}")
                        return None

                    data = await resp.json()

                    if not data or "images" not in data or not data["images"]:
                        return None

                    return data["images"][0]

        except Exception:
            logger.exception("Error Fetching From Waifu.im API")
            return None

    @discord.slash_command(name="waifu", description="Get A Random Waifu Image")
    @option(
        "tag",
        description="Choose A Waifu Category",
        choices=WAIFU_CATEGORIES,
        required=False,
        default="waifu",
    )
    async def waifu_cmd(self, ctx: discord.ApplicationContext, tag: str = "waifu"):
        try:
            await ctx.defer()

            if tag not in WAIFU_CATEGORIES:
                logger.error(f"Invalid Category : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"Invalid Category.\n### Please Choose From:\n\n{' | '.join(WAIFU_CATEGORIES)}",
                        color=discord.Color.red(),
                    )
                )

            image = await self.fetch_waifu([tag], nsfw=False)
            if not image:
                logger.error(f"Invalid Category Or API Error : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Invalid Category Or API Error.\n### Please Try Again Later.",
                        color=discord.Color.red(),
                    )
                )

            try:
                if self.db:
                    waifu_api_id = (
                        image.get("image_id")
                        or image.get("image_id")
                        or image.get("signature")
                    )
                    artist = image.get("artist") or {}
                    tags = [t.get("name") for t in image.get("tags", [])]
                    self.db.add_waifu(
                        waifu_api_id,
                        image.get("url"),
                        image.get("preview_url"),
                        image.get("source"),
                        artist.get("name") if isinstance(artist, dict) else None,
                        artist.get("twitter") if isinstance(artist, dict) else None,
                        bool(image.get("is_nsfw", False)),
                        json.dumps(tags),
                    )
                    waifu_row = self.db.get_waifu_by_api_id(waifu_api_id)
                    waifu_db_id = waifu_row[0] if waifu_row else None
                else:
                    waifu_db_id = None

            except Exception:
                logger.exception("Failed saving waifu to DB")
                waifu_db_id = None

            embed = discord.Embed(
                title=f"✨ Oni Chann ~ {tag.capitalize()}!",
                color=discord.Color.random(),
            )
            embed.set_image(url=image.get("url"))

            artist = image.get("artist") or {}
            if artist:
                embed.add_field(
                    name="Artist", value=artist.get("name") or "Unknown", inline=True
                )
            tags_list = (
                ", ".join([t.get("name") for t in image.get("tags", [])]) or "None"
            )
            embed.add_field(name="Tags", value=tags_list, inline=True)
            embed.set_footer(
                text=f"Requested By {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            view = ClaimView(self, waifu_db_id)

            await ctx.respond(embed=embed, view=view)
            logger.info(f"Sent Waifu Image ( {tag.capitalize()} ) To {ctx.author.name}")

        except Exception as e:
            logger.exception("Error In Waifu Command Execution : %s", e)
            await ctx.respond(
                discord.Embed(
                    title="❌ Error",
                    description=f"An Error Occurred While Fetching The Waifu Image.\n```{e}```",
                    color=discord.Color.red(),
                )
            )

    @discord.slash_command(name="nwaifu", description="Get A Random NSFW Waifu Image")
    @option(
        "tag",
        description="Choose A NSFW Waifu Category",
        choices=NWAIFU_CATEGORIES,
        required=False,
        default="hentai",
    )
    async def nsfw_waifu_cmd(
        self, ctx: discord.ApplicationContext, tag: str = "hentai"
    ):
        try:
            await ctx.defer()

            if tag not in NWAIFU_CATEGORIES:
                logger.error(f"Invalid Category : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"Invalid Category.\n### Please Choose From:\n\n{' | '.join(NWAIFU_CATEGORIES)}",
                        color=discord.Color.red(),
                    )
                )

            image = await self.fetch_waifu([tag], nsfw=True)
            if not image:
                logger.error(f"Invalid Category Or API Error : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Invalid Category Or API Error.\n### Please Try Again Later.",
                        color=discord.Color.red(),
                    )
                )
            # save to DB
            try:
                if self.db:
                    waifu_api_id = image.get("image_id") or image.get("signature")
                    artist = image.get("artist") or {}
                    tags = [t.get("name") for t in image.get("tags", [])]
                    self.db.add_waifu(
                        waifu_api_id,
                        image.get("url"),
                        image.get("preview_url"),
                        image.get("source"),
                        artist.get("name") if isinstance(artist, dict) else None,
                        artist.get("twitter") if isinstance(artist, dict) else None,
                        bool(image.get("is_nsfw", False)),
                        json.dumps(tags),
                    )
                    waifu_row = self.db.get_waifu_by_api_id(waifu_api_id)
                    waifu_db_id = waifu_row[0] if waifu_row else None
                else:
                    waifu_db_id = None
            except Exception:
                logger.exception("Failed saving waifu to DB")
                waifu_db_id = None

            embed = discord.Embed(
                title=f"✨ Oni Chann ~ {tag.capitalize()}!",
                color=discord.Color.random(),
            )
            embed.set_image(url=image.get("url"))
            artist = image.get("artist") or {}
            if artist:
                embed.add_field(
                    name="Artist", value=artist.get("name") or "Unknown", inline=True
                )
            tags_list = (
                ", ".join([t.get("name") for t in image.get("tags", [])]) or "None"
            )
            embed.add_field(name="Tags", value=tags_list, inline=True)
            embed.set_footer(
                text=f"Requested By {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            view = ClaimView(self, waifu_db_id)

            await ctx.respond(embed=embed, view=view)
            logger.info(
                f"Sent NSFW Waifu Image ( {tag.capitalize()} ) To {ctx.author.name}"
            )

        except Exception as e:
            logger.exception("Error In NSFW Waifu Command Execution : %s", e)
            await ctx.respond(
                discord.Embed(
                    title="❌ Error",
                    description=f"An Error Occurred While Fetching The Waifu Image.\n```{e}```",
                    color=discord.Color.red(),
                )
            )


class ClaimView(discord.ui.View):
    def __init__(self, cog: Waifu, waifu_db_id: int | None):
        super().__init__(timeout=None)
        self.cog = cog
        self.waifu_db_id = waifu_db_id

    @discord.ui.button(
        label="", style=discord.ButtonStyle.secondary, custom_id="claim_waifu", emoji="♥️"
    )
    async def claim_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        # Basic Checks
        user = interaction.user
        if not self.cog.db:
            return await interaction.response.send_message(
                "Database Unavailable.", ephemeral=True
            )

        # Check If Waifu Exsist In DB
        if not self.waifu_db_id:
            return await interaction.response.send_message(
                "This Waifu Cannot Be Claimed!", ephemeral=True
            )

        # Cooldown Check
        last = self.cog.db.get_last_claim_time(user.id)
        if last and last[0]:
            try:
                last_time = datetime.datetime.strptime(last[0], "%Y-%m-%d %H:%M:%S")
                now = datetime.datetime.utcnow()

                elapsed = (now - last_time).total_seconds()
                cooldown_end = int(time.time() + (self.cog.claim_cooldown - elapsed))

                if elapsed < self.cog.claim_cooldown:
                    return await interaction.response.send_message(
                        f"You Can Claim Every 2 Hours."
                        f"Try Again At <t:{cooldown_end}:R>.",
                        ephemeral=True,
                    )
            except Exception:
                pass

        # Check If Waifu Already Claimed
        if self.cog.db.is_waifu_claimed(self.waifu_db_id):
            return await interaction.response.send_message(
                "This Waifu Is Already Claimed!", ephemeral=True
            )

        try:
            self.cog.db.add_user(user.id, str(user))

            user_row = self.cog.db.get_user(user.id)
            internal_user_id = user_row[0] if user_row else None
            current_count = user_row[3] if user_row and len(user_row) > 3 else 0
            new_count = (current_count or 0) + 1

            self.cog.db.update_user_waifu_count(user.id, new_count)

            waifu_internal_id = self.waifu_db_id

            if internal_user_id is None or waifu_internal_id is None:
                raise RuntimeError("Invalid User Or Waifu ID")

            self.cog.db.add_claim(internal_user_id, waifu_internal_id)
            self.cog.db.update_last_claim(user.id)
        except Exception:
            logger.exception("Error While Processing Claim")
            return await interaction.response.send_message(
                "Failed To Claim Waifu Due To Internal Error!", ephemeral=True
            )

        try:
            msg = interaction.message
            embed = (
                msg.embeds[0] if msg.embeds else discord.Embed(title="Waifu Claimed")
            )
            embed.set_footer(
                text=f"Claimed By {user.display_name} 🫶",
                icon_url=user.display_avatar.url,
            )
            await msg.edit(embed=embed, view=None)
        except Exception:
            logger.exception("Failed to edit message after claim")

        await interaction.response.send_message(
            "You Claimed This Waifu! 🫶", ephemeral=True
        )


class PagesView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.page = 0
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.page = (self.page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.page = (self.page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)


def setup(bot):
    logger.info("Loaded : Waifu Cog")
    bot.add_cog(Waifu(bot))
