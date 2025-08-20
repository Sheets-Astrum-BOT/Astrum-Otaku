import discord
import aiohttp
from discord import option
from discord.ext import commands
from extensions.logger import setup_logger

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


class Waifu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch(self, tags, nsfw=False):
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

                    return data["images"][0]["url"]

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

            img_url = await self.fetch([tag], nsfw=False)
            if not img_url:
                logger.error(f"Invalid Category Or API Error : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Invalid Category Or API Error.\n### Please Try Again Later.",
                        color=discord.Color.red(),
                    )
                )

            embed = discord.Embed(
                title=f"✨ Oni Chann ~ {tag.capitalize()}!",
                color=discord.Color.random(),
            )
            embed.set_image(url=img_url)
            embed.set_footer(
                text=f"Requested By {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            await ctx.respond(embed=embed)
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

            img_url = await self.fetch([tag], nsfw=True)
            if not img_url:
                logger.error(f"Invalid Category Or API Error : {tag}")
                return await ctx.respond(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Invalid Category Or API Error.\n### Please Try Again Later.",
                        color=discord.Color.red(),
                    )
                )

            embed = discord.Embed(
                title=f"✨ Oni Chann ~ {tag.capitalize()}!",
                color=discord.Color.random(),
            )
            embed.set_image(url=img_url)
            embed.set_footer(
                text=f"Requested By {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            await ctx.respond(embed=embed)
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


def setup(bot):
    logger.info("Loaded : Waifu Cog")
    bot.add_cog(Waifu(bot))
