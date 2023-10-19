import os
from pathlib import Path

import discord
from discord import Message
from discord.ext import commands
from .utils import clear_print


class Tune(commands.Bot):
    def __init__(self):
        self._cogs = [p.stem for p in Path(".").glob("./src/cogs/*.py")]
        super().__init__(
            command_prefix="'",
            case_insensitive=False,
            intents=discord.Intents.all()
        )

    # https://gist.github.com/Rapptz/6706e1c8f23ac27c98cee4dd985c8120#breaking-changes
    async def setup_hook(self) -> None:
        self.loop.create_task(self.setup())

    async def setup(self):
        clear_print("Loading extensions...")
        val = 0
        cogs = len(self._cogs)
        for cog in self._cogs:
            val += 1
            await self.load_extension(f"src.cogs.{cog}")
            clear_print(f"Loading ext: {cog}... {(val / cogs) * 100:.2f}%")
        clear_print("Loaded extensions!")

    def tune(self):
        TOKEN = os.environ['TOKEN']
        print("Starting Tune...")
        self.run(TOKEN, log_handler=None)

    async def shutdown(self):
        clear_print("Shutting down!")
        await self.close()

    async def on_connect(self):
        clear_print(f"Connected to Discord -> {self.latency * 1000:.2f} ms")

    async def on_resumed(self):
        clear_print(f"Re-connected to Discord -> {self.latency * 1000:.2f} ms")

    async def on_disconnect(self):
        clear_print("Disconnected from Discord")

    async def on_ready(self):
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="Tune")
        )
        clear_print("Bot is ready!")

    async def get_prefix(self, content: Message, /):
        # other prefixes
        return commands.when_mentioned_or("'")(self.bot, content)
