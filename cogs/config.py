import os
import json
import discord
from discord import option
from discord.ext import commands
from extensions.logger import setup_logger

logger = setup_logger(__name__)

MEME_CONFIG_PATH = "memesConfig.json"
QUOTES_CONFIG_PATH = "quotesConfig.json"

MEME_DEFAULT_CONFIG = {
    "enabled": False,
    "channel_id": [],
    "interval_minutes": 60,
}


DEFAULT_QUOTES_CONFIG = {
    "enabled": False,
    "channel_id": [],
    "interval_minutes": 60,
}


def load_config():
    if not os.path.exists(MEME_CONFIG_PATH):
        save_config(MEME_DEFAULT_CONFIG)
        return MEME_DEFAULT_CONFIG.copy()
    try:
        with open(MEME_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in MEME_DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
    except Exception:
        logger.exception("Failed Loading Meme Config - Using Defaults")
        return MEME_DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(MEME_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Meme Config")


def load_quotes_config():
    if not os.path.exists(QUOTES_CONFIG_PATH):
        save_quotes_config(DEFAULT_QUOTES_CONFIG)
        return DEFAULT_QUOTES_CONFIG.copy()
    try:
        with open(QUOTES_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_QUOTES_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
    except Exception:
        logger.exception("Failed Loading Quotes Config - Using Defaults")
        return DEFAULT_QUOTES_CONFIG.copy()


def save_quotes_config(cfg):
    try:
        with open(QUOTES_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        logger.exception("Failed Saving Quotes Config")


class Config(commands.Cog):
    config = discord.SlashCommandGroup("config", "Bot Configuration Commands")

    meme = config.create_subgroup("meme", "Configure Meme Posting")
    quote = config.create_subgroup("quote", "Configure Quote Posting")

    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.quotes_config = load_quotes_config()

    async def update_and_confirm(self, ctx, updates: dict):
        self.config.update(updates)
        save_config(self.config)

        desc = "\n".join([f"**{k}** → **{v}**" for k, v in updates.items()])
        await ctx.respond(
            embed=discord.Embed(
                title="⚙️ Meme Config Updated",
                description=desc,
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    async def update_and_confirm_quotes(self, ctx, updates: dict):
        self.quotes_config.update(updates)
        save_quotes_config(self.quotes_config)

        desc = "\n".join([f"**{k}** → **{v}**" for k, v in updates.items()])
        await ctx.respond(
            embed=discord.Embed(
                title="⚙️ Quotes Config Updated",
                description=desc,
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    # ───── MAIN CONFIG COMMAND (help) ─────
    @config.command(name="help", description="Show config help")
    async def config_help(self, ctx: discord.ApplicationContext):
        await ctx.respond(
            "Use `/config meme ...` or `/config quote ...` to manage settings.",
            ephemeral=True,
        )

    # ───── MEME CONFIG ─────
    @meme.command(name="set", description="Set Meme Posting Config")
    @option(
        "toggle",
        description="Enable/Disable Auto Memes",
        required=False,
        choices=["true", "false"],
    )
    @option(
        "channel", discord.TextChannel, description="Channel For Memes", required=False
    )
    @option(
        "interval", int, description="Interval In Minutes (10 Minutes)", required=False
    )
    async def meme_set(
        self,
        ctx: discord.ApplicationContext,
        toggle: str = None,
        channel: discord.TextChannel = None,
        interval: int = None,
    ):
        if not ctx.user.guild_permissions.administrator:
            return await ctx.respond(
                "❌ You Need **Admin** Permissions To Do This.", ephemeral=True
            )

        updates = {}
        if toggle is not None:
            updates["enabled"] = toggle.lower() == "true"

        if channel is not None:
            current = self.config.get("channel_id") or []

            if channel.id not in current:
                current.append(channel.id)

            updates["channel_id"] = current

        if interval is not None:
            if interval < 10:
                return await ctx.respond(
                    "⚠️ Minimum Interval Is **10 Minutes**.", ephemeral=True
                )
            updates["interval_minutes"] = interval

        if updates:
            await self.update_and_confirm(ctx, updates)
        else:
            await ctx.respond("⚠️ No Changes Provided.", ephemeral=True)

    @meme.command(name="show", description="Show Current Meme Config")
    async def meme_show(self, ctx):

        cfg = self.config
        chlist = cfg.get("channel_id") or []
        channel = ", ".join([f"<#{c}>" for c in chlist]) if chlist else "Not Set"

        embed = discord.Embed(
            title="⚙️ Meme Config",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Enabled", value=str(cfg["enabled"]))
        embed.add_field(name="Channel", value=channel)
        embed.add_field(name="Interval", value=f"{cfg['interval_minutes']} minutes")

        await ctx.respond(embed=embed, ephemeral=True)

    # ───── QUOTES CONFIG ─────
    @quote.command(name="set", description="Set Quote Posting Config")
    @option(
        "toggle",
        description="Enable/Disable Quotes",
        required=False,
        choices=["true", "false"],
    )
    @option(
        "channel",
        discord.TextChannel,
        description="Channel For Quotes Autoposting",
        required=False,
    )
    @option(
        "interval", int, description="Interval In Minutes (10 Minutes)", required=False
    )
    async def quote_set(
        self,
        ctx: discord.ApplicationContext,
        toggle: str = None,
        channel: discord.TextChannel = None,
        interval: int = None,
    ):
        if not ctx.user.guild_permissions.administrator:
            return await ctx.respond(
                "❌ You Need **Admin** Permissions To Do This.", ephemeral=True
            )

        updates = {}
        if toggle is not None:
            updates["enabled"] = toggle.lower() == "true"

        if channel is not None:
            current = self.quotes_config.get("channel_id") or []

            if channel.id not in current:
                current.append(channel.id)
            
            updates["channel_id"] = current

        if interval is not None:
            if interval < 10:
                return await ctx.respond(
                    "⚠️ Minimum Interval Is **10 Minutes**.", ephemeral=True
                )
            updates["interval_minutes"] = interval

        if updates:
            await self.update_and_confirm_quotes(ctx, updates)
        else:
            await ctx.respond("⚠️ No Changes Provided.", ephemeral=True)

    @quote.command(name="show", description="Show Current Quote Config")
    async def quote_show(self, ctx):
        cfg = self.quotes_config
        chlist = cfg.get("channel_id") or []
        channel = ", ".join([f"<#{c}>" for c in chlist]) if chlist else "Not Set"

        embed = discord.Embed(
            title="⚙️ Quotes Config",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Enabled", value=str(cfg["enabled"]))
        embed.add_field(name="Channel", value=channel)
        embed.add_field(name="Interval", value=f"{cfg['interval_minutes']} minutes")
        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot):
    logger.info("Loaded : Config Cog")
    bot.add_cog(Config(bot))
