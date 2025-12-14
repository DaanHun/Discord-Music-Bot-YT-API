import os
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio

# Load bot token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Queue dictionary per guild
queues = {}  # {guild_id: [{"title": str, "url": str}, ...]}

# Event: bot ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    print("Slash commands synced!")

# Function: get YouTube audio URL and title
def get_youtube_audio(query):
    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch1",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

        if "entries" in info:
            info = info["entries"][0]

        formats = info.get("formats", [info])
        audio_url = None
        for f in formats:
            if f.get("acodec") != "none":
                audio_url = f["url"]
                break
        if audio_url is None:
            audio_url = info["url"]

        return audio_url, info.get("title", "Unknown Title")

# Function: play the next song in queue
async def play_next(guild_id):
    if guild_id not in queues or not queues[guild_id]:
        # No songs left
        vc = bot.get_guild(guild_id).voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
        return

    vc = bot.get_guild(guild_id).voice_client
    if not vc:
        return

    song = queues[guild_id][0]

    def after_play(error):
        if error:
            print(f"Error playing: {error}")
        # Remove song from queue and play next
        queues[guild_id].pop(0)
        # Schedule next song
        fut = asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(e)

    # Stop any current song
    if vc.is_playing():
        vc.stop()

    vc.play(
        discord.FFmpegPCMAudio(
            song["url"],
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        ),
        after=after_play
    )

# Slash command: /play <query>
@tree.command(name="play", description="Play a song from YouTube")
@app_commands.describe(search="Song name or keywords to search")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("You need to be in a voice channel first!", ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel

    if interaction.guild.voice_client is None:
        vc = await voice_channel.connect()
    else:
        vc = interaction.guild.voice_client
        if vc.channel != voice_channel:
            await vc.move_to(voice_channel)

    try:
        audio_url, title = await asyncio.to_thread(get_youtube_audio, search)

        guild_id = interaction.guild.id
        if guild_id not in queues:
            queues[guild_id] = []

        queues[guild_id].append({"title": title, "url": audio_url})

        # If only one song in queue, start playing
        if len(queues[guild_id]) == 1:
            await play_next(guild_id)

        await interaction.followup.send(f"Added to queue: **{title}**")

    except Exception as e:
        await interaction.followup.send(f"Error: {e}")

# Slash command: /queue - shows the current queue
@tree.command(name="queue", description="Show the current music queue")
async def queue_cmd(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in queues or not queues[guild_id]:
        await interaction.response.send_message("The queue is empty.", ephemeral=True)
        return

    embed = discord.Embed(title="Music Queue", color=discord.Color.blurple())
    for i, song in enumerate(queues[guild_id], start=0):
        if i == 0:
            embed.add_field(name=f"Currently playing: {song['title']}", value="\u200b", inline=False)
        else:
            embed.add_field(name=f"{i}. {song['title']}", value="\u200b", inline=False)

    await interaction.response.send_message(embed=embed)

# Slash command: /skip - skip the current song
@tree.command(name="skip", description="Skip the currently playing song")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    guild_id = interaction.guild.id

    if not vc or not vc.is_connected():
        await interaction.response.send_message("I'm not connected to a voice channel!", ephemeral=True)
        return

    if not vc.is_playing():
        await interaction.response.send_message("No song is currently playing!", ephemeral=True)
        return

    vc.stop()  # Only stop; after_play will handle removing and playing the next
    await interaction.response.send_message("Skipped the current song!")



# Run bot
bot.run(TOKEN)
