import json
import random
import asyncio
import discord
import aiohttp
from discord import option
from discord.ext import commands, tasks
from extensions.logger import setup_logger

logger = setup_logger(__name__)

API_BASE = "https://yurippe.vercel.app/api/quotes"

CONFIG_PATH = "quotesConfig.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "channel_id": [],
    "interval_minutes": 60,
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
        logger.exception("Failed Loading Quotes Config- Using Defaults")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Quotes Config")


class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.auto_task.start()

    def cog_unload(self):
        self.auto_task.cancel()

    async def fetch_quote(self, character=None, show=None, random_one=True):
        params = {}
        if character:
            params["character"] = character
        if show:
            params["show"] = show
        if random_one:
            params["random"] = "1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_BASE, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        raise ValueError(f"API Returned {resp.status}")

                    data = await resp.json()

                    if not isinstance(data, list) or not data:
                        raise ValueError("Unexpected API Response")

                    chosen = random.choice(data)
                    return chosen["quote"], chosen["character"], chosen["show"]
        except Exception as e:
            logger.warning("Quote API Failed, Falling Back : %s", e)
            fallback = random.choice(
                [
                    (
                        "People’s lives don’t end when they die, it ends when they lose faith.",
                        "Itachi Uchiha",
                        "Naruto",
                    ),
                    (
                        "Whatever you lose, you’ll find it again. But what you throw away you’ll never get back.",
                        "Kenshin Himura",
                        "Rurouni Kenshin",
                    ),
                    (
                        "A lesson without pain is meaningless.",
                        "Edward Elric",
                        "Fullmetal Alchemist",
                    ),
                    (
                        "When you hit the point of no return, that’s the moment it truly becomes a journey.",
                        "Hinata Miyake",
                        "A Place Further Than The Universe",
                    ),
                    (
                        "If you don’t take risks, you can’t create a future.",
                        "Monkey D. Luffy",
                        "One Piece",
                    ),
                    (
                        "The world isn’t perfect. But it’s there for us, doing the best it can. That’s what makes it so damn beautiful.",
                        "Roy Mustang",
                        "Fullmetal Alchemist",
                    ),
                ]
            )
            return fallback

    async def make_embed(self, ctx_or_channel, quote, author, show=None):
        requester = getattr(ctx_or_channel, "author", None)
        embed = discord.Embed(
            title="🌸 Anime Quote",
            description=(
                f"### “ {quote} ”\n\n— **{author}** ( {show} )"
                if show
                else f"“### {quote} ”\n\n— ** {author} **"
            ),
            color=discord.Color.random(),
        )
        if requester:
            embed.set_footer(
                text=f"Requested By {requester.name}",
                icon_url=requester.display_avatar.url,
            )
        else:
            embed.set_footer(text="Daily Dose Of Senpai Wisdom ✨")
        return embed

    @discord.slash_command(name="quote", description="Get A Random Anime Quote")
    @option(
        "character",
        description="Filter By Character ( Supports Multiple, Comma-Separated )",
        required=False,
    )
    @option(
        "show",
        description="Filter By Anime / Show ( Supports Multiple, Comma-Separated )",
        required=False,
    )
    async def quote_cmd(
        self, ctx: discord.ApplicationContext, character: str = None, show: str = None
    ):
        try:
            await ctx.defer()
            quote, author, show_name = await self.fetch_quote(
                character=character, show=show
            )
            embed = await self.make_embed(ctx, quote, author, show_name)

            await ctx.respond(embed=embed)
            logger.info(f"Sent Quote To {ctx.author.name}")

        except Exception as e:
            logger.exception("Error In Quote Command : %s", e)
            await ctx.respond(
                embed=discord.Embed(
                    title="❌ Error",
                    description=f"An Error Occurred While Fetching A Quote.\n```{e}```",
                    color=discord.Color.red(),
                )
            )

    @tasks.loop(hours=1)
    async def auto_task(self):
        try:
            cfg = self.config
            if not cfg.get("enabled") or not cfg.get("channel_id", []):
                return
            
            for channel_id in cfg.get("channel_id", []):
                channel = self.bot.get_channel(channel_id)

                if not channel:
                    logger.warning("Configured Quotes Channel Not Found - Disabling")
                    cfg["enabled"] = False
                    save_config(cfg)
                    return
                
                quote, author, show = await self.fetch_quote()
                embed = await self.make_embed(channel, quote, author, show)
                
                await channel.send(embed=embed)
                
                logger.info(f"Auto Posted Quote To {channel.id}")
                interval = max(10, int(cfg.get("interval_minutes", 180)))
                extra = interval - 5
                
                if extra > 0:
                    await asyncio.sleep(extra * 60)
        
        except Exception:
            logger.exception("Error In Auto Quote Task")

    @auto_task.before_loop
    async def before_auto(self):
        await self.bot.wait_until_ready()


def setup(bot):
    logger.info("Loaded : Quotes Cog")
    bot.add_cog(Quotes(bot))
