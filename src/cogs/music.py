import discord
import wavelink
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands._types import BotT
from discord import Member, VoiceState, DMChannel, Guild

from typing import Union
from logging import getLogger


logger = getLogger("discord")
EMBED_COLOR = discord.Color.magenta()


class TPlayer(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def destroy(self, idf: Union[Context, Guild]):
        if isinstance(idf, Context):
            guild_id = idf.guild.id
        elif isinstance(idf, Guild):
            guild_id = idf.id
        await self._destroy(guild_id)


class MusicCog(commands.Cog):
    __cog_name__ = "Music"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        # check if no members (not bot) in vc
        if not member.bot and after.channel is None:
            if not [m for m in before.channel.members if not m.bot]:
                pass  # disconnect the bot

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logger.info(f"Wavelink node {node.id} ready.")

    async def cog_check(self, ctx: Context[BotT]) -> bool:
        if isinstance(ctx.channel, DMChannel):
            await ctx.send("Music is not supported in DMs.")
            return False
        return True

    async def cog_load(self) -> None:
        await self.start_nodes()

    async def start_nodes(self):
        node = wavelink.Node(uri='http://localhost:2333', password='youshallnotpass')
        await wavelink.NodePool.connect(client=self.bot, nodes=[node])

    def get_player(self, idf: Union[Context, Guild]):
        node = wavelink.NodePool.get_node()
        if isinstance(idf, Context):
            return node.get_player(idf.guild.id)
        elif isinstance(idf, Guild):
            return node.get_player(idf.id)



async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
