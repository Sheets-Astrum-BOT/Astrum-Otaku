import os
import asyncio
import discord
import datetime
from dotenv import load_dotenv
from discord.ext import commands
from extensions.database import database
from extensions.logger import setup_logger


load_dotenv()
logger = setup_logger()

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    timeNow = datetime.datetime.now()

    logger.info("-------------------------------")
    logger.info(f"Logged In : {bot.user}")
    logger.info(f"User ID   : {bot.user.id}")
    logger.info("-------------------------------")
    logger.info(f"Time      : {timeNow.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("-------------------------------")
    logger.info(f"Guilds    : {len(bot.guilds)}")
    logger.info("-------------------------------")
    logger.info("Bot Is Ready!")
    logger.info("-------------------------------")

    logger.info("Setting Up Database ~ ")
    database("astrumotaku.db")
    logger.info("Database Setup Complete")

    logger.info("-------------------------------")

    await bot.change_presence(activity=discord.Game("With Waifus ❤️"))


async def load_extensions():
    logger.info("------ Loading Extensions -----")
    bot.load_extension("cogs.waifu")
    bot.load_extension("cogs.memes")
    bot.load_extension("cogs.quotes")
    bot.load_extension("cogs.config")


async def main():
    async with bot:
        await load_extensions()
        await bot.start(os.getenv("TOKEN"))


if __name__ == "__main__":
    asyncio.run(main())
