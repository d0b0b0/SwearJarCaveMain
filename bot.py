import os
import json
import re
import io

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ==============================
# 1. Load token from .env
# ==============================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
print("TOKEN:", repr(TOKEN))

if not TOKEN:
    raise SystemExit("❌ Bot token not found! Check your .env (DISCORD_TOKEN).")


# ==============================
# 2. Intents
# ==============================

intents = discord.Intents.default()
intents.message_content = True   # required to read message text
intents.members = True


# ==============================
# 3. Bot instance
# ==============================

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)


# ==============================
# 4. Files & default data
# ==============================

STATS_FILE = "swear_stats.json"   # per-guild stats
WORDS_FILE = "swear_words.json"   # global swear words

DEFAULT_SWEARS = [
    # English
    "fuck", "shit", "bitch", "asshole", "bastard", "damn",
    # Russian
    "блять", "блядь", "сука", "пидор", "хуй", "хер", "ебать", "ебаный", "ёбаный",
    "бля", "мразь", "пидорас", "мудак", "долбоёб", "долбоеб",
    "ублюдок", "гандон", "гондон", "шлюха", "проститутка",
]


def load_json(path: str, default: dict) -> dict:
    """Load JSON from file or return default."""
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


# stats_data = { "guilds": { guild_id: { "users": {...}, "total": int } } }
stats_data = load_json(STATS_FILE, {"guilds": {}})
if "guilds" not in stats_data:
    stats_data = {"guilds": {}}
    save_json(STATS_FILE, stats_data)


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


# ============ global swear words ============

def load_swears() -> dict:
    """
    Global swear words list.

    File format (new):
    { "words": [ ... ] }

    If old format with "guilds" is detected, it will be merged.
    """
    if not os.path.exists(WORDS_FILE):
        return {"words": DEFAULT_SWEARS.copy()}

    try:
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"words": DEFAULT_SWEARS.copy()}

    # Old format: { "guilds": { ... } }
    if "guilds" in data and "words" not in data:
        merged = set()
        for g in data["guilds"].values():
            merged.update([w.lower() for w in g.get("words", [])])
        if not merged:
            merged = set(DEFAULT_SWEARS)
        return {"words": sorted(merged)}

    # New format
    if "words" in data:
        return data

    return {"words": DEFAULT_SWEARS.copy()}


def save_swears(swears_dict: dict):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(swears_dict, f, ensure_ascii=False, indent=2)


swear_data = load_swears()
SWEAR_WORDS = {w.lower() for w in swear_data["words"]}


# ==============================
# 5. Swear detection
# ==============================

def count_swears(text: str, swear_words: set[str]) -> int:
    """Return number of swear words in text."""
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
# 7. Message listener
# ==============================

@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id
    guild_stats = get_guild_stats(guild_id)

    swear_count = count_swears(message.content, SWEAR_WORDS)

    if swear_count > 0:
        user_id = str(message.author.id)

        if user_id not in guild_stats["users"]:
            guild_stats["users"][user_id] = {
                "count": 0,
                "name": f"{message.author.name}#{message.author.discriminator}"
            }

        guild_stats["users"][user_id]["count"] += swear_count
        guild_stats["total"] += swear_count

        save_json(STATS_FILE, stats_data)

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

    embed.add_field(
        name="/help",
        value="Show this help menu.",
        inline=False
    )
    embed.add_field(
        name="!swearme",
        value="Show how many swears you said on this server.",
        inline=False
    )
    embed.add_field(
        name="!sweartop",
        value="Show top users by swears on this server.",
        inline=False
    )
    embed.add_field(
        name="!sweartotal",
        value="Show total number of swears on this server.",
        inline=False
    )
    embed.add_field(
        name="/addswear <word>",
        value="Add a swear word to the global list (admin only).",
        inline=False
    )
    embed.add_field(
        name="/removeswear <word>",
        value="Remove a swear word from the global list (admin only).",
        inline=False
    )
    embed.add_field(
        name="/listswears",
        value="Show all globally tracked swear words.",
        inline=False
    )

    embed.set_footer(
        text="SwearJarCove — tracks both Russian and English swear words (global word list, per-server stats) 🙂"
    )

    await interaction.response.send_message(embed=embed)


# ==============================
# 9. Slash commands: manage global swear list
# ==============================

@bot.tree.command(name="addswear", description="Add a swear word (admin only, global)")
async def add_swear(interaction: discord.Interaction, word: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Only admins can use this command.",
            ephemeral=True
        )

    global SWEAR_WORDS, swear_data

    w = word.lower()
    if w in SWEAR_WORDS:
        return await interaction.response.send_message(
            f"⚠️ `{word}` is already in the global swear list."
        )

    SWEAR_WORDS.add(w)
    swear_data["words"].append(w)
    save_swears(swear_data)

    await interaction.response.send_message(
        f"✅ Added global swear word: **{word}**"
    )


@bot.tree.command(name="removeswear", description="Remove a swear word (admin only, global)")
async def remove_swear(interaction: discord.Interaction, word: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Only admins can use this command.",
            ephemeral=True
        )

    global SWEAR_WORDS, swear_data

    w = word.lower()
    if w not in SWEAR_WORDS:
        return await interaction.response.send_message(
            f"⚠️ `{word}` is not in the global swear list."
        )

    SWEAR_WORDS.remove(w)
    swear_data["words"] = [x for x in swear_data["words"] if x.lower() != w]
    save_swears(swear_data)

    await interaction.response.send_message(
        f"🗑️ Removed global swear word: **{word}**"
    )


@bot.tree.command(name="listswears", description="Show all global swear words")
async def list_swears(interaction: discord.Interaction):
    words = sorted(SWEAR_WORDS)
    if not words:
        return await interaction.response.send_message(
            "No swear words configured.",
            ephemeral=True
        )

    text = ", ".join(words)
    embed = discord.Embed(
        title="📝 Global tracked swear words",
        description=text,
        color=0xFFD166
    )
    await interaction.response.send_message(embed=embed)


# ==============================
# 10. Prefix commands (per-server stats)
# ==============================

@bot.command(name="swearme")
async def swear_me(ctx: commands.Context):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    guild_stats = get_guild_stats(ctx.guild.id)
    user_id = str(ctx.author.id)

    if user_id not in guild_stats["users"]:
        return await ctx.send(
            f"{ctx.author.mention}, you haven't said any swear words on this server yet 😇"
        )

    count = guild_stats["users"][user_id]["count"]
    await ctx.send(
        f"{ctx.author.mention}, you said **{count}** swear words on this server."
    )


@bot.command(name="sweartop")
async def swear_top(ctx: commands.Context, limit: int = 10):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    # защита от странных значений
    if limit < 1:
        limit = 10
    if limit > 25:
        limit = 25

    guild_stats = get_guild_stats(ctx.guild.id)
    users = guild_stats["users"]

    if not users:
        return await ctx.send("Nobody has used swear words on this server yet 🤔")

    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )[:limit]

    # готовим красивые строки для описания
    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉"
    }

    lines = []
    for i, (uid, info) in enumerate(sorted_users, start=1):
        member = ctx.guild.get_member(int(uid))
        # если юзер всё ещё на сервере — упоминаем его
        if member:
            name = member.mention
        else:
            # иначе используем сохранённое имя
            name = info["name"]

        medal = medals.get(i, "🔹")
        count = info["count"]

        # можно чуть подсветить топовых и больших матерщинников
        lines.append(f"{medal} **{i}. {name}** — `{count}` swear(s)")

    description = "\n".join(lines)

    # делаем embed
    embed = discord.Embed(
        title=f"🏆 Swear leaderboard — {ctx.guild.name}",
        description=description,
        color=0xFF5C5C
    )

    total_swears = guild_stats.get("total", 0)
    embed.add_field(
        name="📊 Total swears on this server",
        value=f"**{total_swears}**",
        inline=False
    )

    embed.add_field(
        name="🤖 Tip",
        value="Use `!swearme` to check your own stats.\nUse `/listswears` to see tracked words.",
        inline=False
    )

    # красивая иконка сервера, если есть
    try:
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
    except Exception:
        pass

    embed.set_footer(
        text=f"SwearJarCove — tracking {len(SWEAR_WORDS)} swear words globally"
    )

    await ctx.send(embed=embed)


@bot.command(name="sweartotal")
async def swear_total(ctx: commands.Context):
    if ctx.guild is None:
        return await ctx.send("This command can only be used in a server.")

    guild_stats = get_guild_stats(ctx.guild.id)
    total = guild_stats["total"]
    await ctx.send(
        f"Total swear words on this server: **{total}**"
    )

# ===== SEND swear_words.json =====

@bot.command(name="export_swears")
@commands.is_owner()
async def export_swears(ctx):
    try:
        with open("swear_words.json", "r", encoding="utf-8") as f:
            data = f.read()

        await ctx.send(
            "📤 Exported **swear_words.json**",
            file=discord.File(io.BytesIO(data.encode("utf-8")), filename="swear_words.json")
        )
    except Exception as e:
        await ctx.send(f"❌ Error exporting swear_words.json:\n```{e}```")


# ===== SEND swear_stats.json =====

@bot.command(name="export_stats")
@commands.is_owner()
async def export_stats(ctx):
    try:
        with open("swear_stats.json", "r", encoding="utf-8") as f:
            data = f.read()

        await ctx.send(
            "📤 Exported **swear_stats.json**",
            file=discord.File(io.BytesIO(data.encode("utf-8")), filename="swear_stats.json")
        )
    except Exception as e:
        await ctx.send(f"❌ Error exporting swear_stats.json:\n```{e}```")


# ===== SEND BOTH FILES =====

@bot.command(name="export_all")
@commands.is_owner()
async def export_all(ctx):
    try:
        with open("swear_words.json", "r", encoding="utf-8") as f1:
            words = f1.read()
        with open("swear_stats.json", "r", encoding="utf-8") as f2:
            stats = f2.read()

        files = [
            discord.File(io.BytesIO(words.encode("utf-8")), filename="swear_words.json"),
            discord.File(io.BytesIO(stats.encode("utf-8")), filename="swear_stats.json")
        ]

        await ctx.send("📤 Exported **both files**:", files=files)

    except Exception as e:
        await ctx.send(f"❌ Error exporting files:\n```{e}```")

# ==============================
# 11. Run bot
# ==============================

bot.run(TOKEN)
