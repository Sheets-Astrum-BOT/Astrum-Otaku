import json
import random
import asyncio
import discord
import aiohttp
from discord.ext import commands, tasks
from extensions.logger import setup_logger

logger = setup_logger(__name__)

API_URL = "https://meme-api.com/gimme/animememes"

CONFIG_PATH = "memesConfig.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "channel_id": None,
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
        logger.exception("Failed Loading Memes Config - Using Defaults")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Memes Config")


class AnimeMemes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.auto_task.start()

    def cog_unload(self):
        self.auto_task.cancel()

    async def fetch_meme(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, timeout=10) as resp:
                    if resp.status != 200:
                        raise ValueError(f"API Returned {resp.status}")

                    data = await resp.json()
                    return data["url"], data["title"], data["postLink"], data["author"]

        except Exception as e:
            logger.warning("Meme API Failed, Falling Back : %s", e)
            fallback = random.choice(
                [
                    (
                        "https://i.redd.it/zw86cnjls1u51.jpg",
                        "Itachi knows the pain",
                        "https://reddit.com/r/animememes",
                        "fallback_meme",
                    ),
                    (
                        "https://i.redd.it/8h9j34u5yab41.jpg",
                        "Luffy logic",
                        "https://reddit.com/r/animememes",
                        "fallback_meme",
                    ),
                    (
                        "https://i.redd.it/bv4rhv3u0vb81.jpg",
                        "Classic DBZ energy",
                        "https://reddit.com/r/animememes",
                        "fallback_meme",
                    ),
                ]
            )
            return fallback

    async def make_embed(self, ctx_or_channel, img_url, title, post_url, author):
        requester = getattr(ctx_or_channel, "author", None)
        embed = discord.Embed(
            title=f"😂 Anime Meme - {title}",
            description=f"**Author : ** u/{author}**\n",
            url=post_url,
            color=discord.Color.random(),
        )
        embed.set_image(url=img_url)
        embed.set_footer(
            text=(
                f"Requested By {requester.name}"
                if requester
                else "Daily Dose of Weeb Humor ✨"
            ),
            icon_url=(
                getattr(requester, "display_avatar", None).url
                if requester
                else discord.Embed.Empty
            ),
        )
        return embed

    @discord.slash_command(name="meme", description="Get A Random Anime Meme")
    async def animeme_cmd(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()
            img_url, title, post_url, author = await self.fetch_meme()
            embed = await self.make_embed(ctx, img_url, title, post_url, author)

            await ctx.respond(embed=embed)
            logger.info(f"Sent Meme To {ctx.author.name}")

        except Exception as e:
            logger.exception("Error In Meme Command : %s", e)
            await ctx.respond(
                embed=discord.Embed(
                    title="❌ Error",
                    description=f"An Error Occurred While Fetching A Meme.\n```{e}```",
                    color=discord.Color.red(),
                )
            )

    @tasks.loop(hours=1)
    async def auto_task(self):
        try:
            cfg = self.config
            if not cfg.get("enabled") or not cfg.get("channel_id"):
                return

            channel = self.bot.get_channel(cfg.get("channel_id"))
            if not channel:
                logger.warning("Configured Memes Channel Not Found - Disabling")
                cfg["enabled"] = False
                save_config(cfg)
                return

            img_url, title, post_url, author = await self.fetch_meme()
            embed = await self.make_embed(channel, img_url, title, post_url, author)

            await channel.send(embed=embed)
            logger.info(f"Auto Posted Meme To {channel.id}")

            interval = max(10, int(cfg.get("interval_minutes", 180)))
            extra = interval - 5
            if extra > 0:
                await asyncio.sleep(extra * 60)

        except Exception:
            logger.exception("Error In Auto Meme Task")

    @auto_task.before_loop
    async def before_auto(self):
        await self.bot.wait_until_ready()


def setup(bot):
    logger.info("Loaded : Memes Cog")
    bot.add_cog(AnimeMemes(bot))
