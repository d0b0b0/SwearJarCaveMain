import os
import json
import re

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ==============================
# 1. Load token
# ==============================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
print("TOKEN:", repr(TOKEN))

if not TOKEN:
    raise SystemExit("❌ Bot token not found! Check your .env file (DISCORD_TOKEN).")


# ==============================
# 2. Intents
# ==============================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# ==============================
# 3. Bot instance
# ==============================

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ==============================
# 4. Files and default data
# ==============================

STATS_FILE = "swear_stats.json"
WORDS_FILE = "swear_words.json"

DEFAULT_SWEARS = [
    # English
    "fuck", "shit", "bitch", "asshole", "bastard", "damn",
    # Russian
    "блять", "блядь", "сука", "пидор", "хуй", "хер", "ебать", "ебаный", "ёбаный",
    "бля", "мразь", "пидорас", "мудак", "долбоёб", "долбоеб",
    "ублюдок", "гандон", "гондон", "шлюха", "проститутка",
]


def load_json(path: str, default: dict) -> dict:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Глобальные структуры:
# stats_data = { "guilds": { guild_id: { "users": {...}, "total": int } } }
# words_data = { "guilds": { guild_id: { "words": [ ... ] } } }

stats_data = load_json(STATS_FILE, {"guilds": {}})
words_data = load_json(WORDS_FILE, {"guilds": {}})


def get_guild_stats(guild_id: int) -> dict:
    """Return stats dict for this guild, create if missing."""
    gid = str(guild_id)
    if gid not in stats_data["guilds"]:
        stats_data["guilds"][gid] = {
            "users": {},
            "total": 0
        }
        save_json(STATS_FILE, stats_data)
    return stats_data["guilds"][gid]


def get_guild_words(guild_id: int) -> set:
    """Return set of swear words for this guild, create with defaults if missing."""
    gid = str(guild_id)
    if gid not in words_data["guilds"]:
        words_data["guilds"][gid] = {
            "words": DEFAULT_SWEARS.copy()
        }
        save_json(WORDS_FILE, words_data)

    words_list = words_data["guilds"][gid]["words"]
    return {w.lower() for w in words_list}


def set_guild_words(guild_id: int, words: list[str]):
    """Update word list for guild and save."""
    gid = str(guild_id)
    words_data["guilds"][gid] = {"words": words}
    save_json(WORDS_FILE, words_data)


# ==============================
# 5. Swear detection
# ==============================

def count_swears(text: str, swear_words: set[str]) -> int:
    text = text.lower()
    text = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", " ", text)
    words = text.split()

    count = 0
    for word in words:
        for swear in swear_words:
            if swear in word:
                count += 1
                break
    return count


# ==============================
# 6. Bot ready
# ==============================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot logged in as {bot.user}")
    print("🔧 Slash commands synced.")


# ==============================
# 7. Message listener (per guild)
# ==============================

@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id
    guild_stats = get_guild_stats(guild_id)
    guild_swears = get_guild_words(guild_id)

    swear_count = count_swears(message.content, guild_swears)

    if swear_count > 0:
        user_id = str(message.author.id)

        if user_id not in guild_stats["users"]:
            guild_stats["users"][user_id] = {
                "count": 0,
                "name": f"{message.author.name}#{message.author.discriminator}"
            }

        guild_stats["users"][user_id]["count"] += swear_count
        guild_stats["total"] += swear_count

        # Save stats
        save_json(STATS_FILE, stats_data)

        try:
            await message.add_reaction("🧠")
        except Exception:
            pass

    await bot.process_commands(message)


# ==============================
# 8. /help (nice embed)
# ==============================

@bot.tree.command(name="help", description="Show the bot command list")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📘 SwearJarCove Bot Commands",
        description="List of all available commands:",
        color=0x4A90E2
    )

    embed.add_field(name="/help", value="Show this help menu.", inline=False)
    embed.add_field(name="!swearme", value="Show how many swears you said.", inline=False)
    embed.add_field(name="!sweartop", value="Show top users by swears on this server.", inline=False)
    embed.add_field(name="!sweartotal", value="Show total swears on this server.", inline=False)
    embed.add_field(name="/addswear <word>", value="Add a swear word to this server (admin only).", inline=False)
    embed.add_field(name="/removeswear <word>", value="Remove a swear word on this server (admin only).", inline=False)
    embed.add_field(name="/listswears", value="Show all tracked swear words on this server.", inline=False)

    embed.set_footer(text="SwearJarCove — tracks both Russian and English swear words per server 🙂")

    await interaction.response.send_message(embed=embed)


# ==============================
# 9. Slash commands: manage swear words per server
# ==============================

@bot.tree.command(name="addswear", description="Add a swear word for this server (admin only)")
async def add_swear(interaction: discord.Interaction, word: str):
    if interaction.guild is None:
        return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only server admins can use this command.", ephemeral=True)

    guild_id = interaction.guild.id
    guild_words = list(get_guild_words(guild_id))
    lower_set = {w.lower() for w in guild_words}
    w = word.lower()

    if w in lower_set:
        return await interaction.response.send_message(f"⚠️ `{word}` is already in the swear list for this server.")

    guild_words.append(w)
    set_guild_words(guild_id, guild_words)

    await interaction.response.send_message(f"✅ Added swear word for this server: **{word}**")


@bot.tree.command(name="removeswear", description="Remove a swear word for this server (admin only)")
async def remove_swear(interaction: discord.Interaction, word: str):
    if interaction.guild is None:
        return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only server admins can use this command.", ephemeral=True)

    guild_id = interaction.guild.id
    guild_words = list(get_guild_words(guild_id))
    lower_set = {w.lower() for w in guild_words}
    w = word.lower()

    if w not in lower_set:
        return await interaction.response.send_message(f"⚠️ `{word}` is not in the swear list for this server.")

    # remove by matching lower
    new_words = [x for x in guild_words if x.lower() != w]
    set_guild_words(guild_id, new_words)

    await interaction.response.send_message(f"🗑️ Removed swear word for this server: **{word}**")


@bot.tree.command(name="listswears", description="Show all swear words for this server")
async def list_swears(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)

    guild_id = interaction.guild.id
    guild_words = sorted(get_guild_words(guild_id))

    if not guild_words:
        return await interaction.response.send_message("No swear words configured for this server.")

    text = ", ".join(guild_words)
    embed = discord.Embed(
        title="📝 Tracked swear words for this server",
        description=text,
        color=0xFFD166
    )
    await interaction.response.send_message(embed=embed)


# ==============================
# 10. Prefix commands (per server)
# ==============================

@bot.command(name="swearme")
async def swear_me(ctx: commands.Context):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    guild_stats = get_guild_stats(ctx.guild.id)
    user_id = str(ctx.author.id)

    if user_id not in guild_stats["users"]:
        return await ctx.send(f"{ctx.author.mention}, you haven't said any swear words on this server yet 😇")

    count = guild_stats["users"][user_id]["count"]
    await ctx.send(f"{ctx.author.mention}, you said **{count}** swear words on this server.")


@bot.command(name="sweartop")
async def swear_top(ctx: commands.Context, limit: int = 10):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    guild_stats = get_guild_stats(ctx.guild.id)
    users = guild_stats["users"]

    if not users:
        return await ctx.send("Nobody has used swear words on this server yet 🤔")

    sorted_users = sorted(users.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]
    lines = []

    for i, (uid, info) in enumerate(sorted_users, start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else info["name"]
        lines.append(f"**{i}. {name}** — {info['count']}")

    await ctx.send("\n".join(lines))


@bot.command(name="sweartotal")
async def swear_total(ctx: commands.Context):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    guild_stats = get_guild_stats(ctx.guild.id)
    total = guild_stats["total"]
    await ctx.send(f"Total swear words on this server: **{total}**")


# ==============================
# 11. Run bot
# ==============================

bot.run(TOKEN)
