import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands._types import BotT
from discord import Member, VoiceState, DMChannel, Guild

from wavelink.types.track import Track
from wavelink import Node, NodePool, Player, Playable, TrackSource, YouTubeTrack

from typing import Union
from logging import getLogger

logger = getLogger("discord")
EMBED_COLOR = discord.Color.magenta()


class TPlayer(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def destroy(self):
        if self.is_connected():
            await self.disconnect()
        await self._destroy()


class TTrack(Playable):
    # default YouTube
    PREFIX = "ytsearch:"
    PREFIXES = ["ytsearch:", "ytpl:", "ytmsearch:", "scsearch:"]

    def __init__(self, ctx: Context, data: Track):
        super().__init__(data)
        self.thumb = None
        self.parsed_duration = self.parse_duration(self.length)
        self.requester = ctx.author
        self.channel = ctx.channel

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append('{} days'.format(int(days)))
        if hours > 0:
            duration.append('{} hours'.format(int(hours)))
        if minutes > 0:
            duration.append('{} minutes'.format(int(minutes)))
        if seconds > 0:
            duration.append('{} seconds'.format(int(seconds)))

        return ', '.join(duration)

    async def fetch_thumbnail(self):
        if self.source == TrackSource.YouTube:
            self.thumb = await YouTubeTrack.fetch_thumbnail(self)
        elif self.source == TrackSource.SoundCloud:
            self.thumb = ("https://r1.hiclipart.com/path/310/259/692/ksnhqtqg0mddtjejjea3rprovf"
                          "-8f54861ffbc19d4eb264ce3a6740cdd6.png")
        else:
            self.thumb = ("https://cdn.discordapp.com/avatars/980092225960702012/7bd37b51889111531a4ee267d05f48dd.png"
                          "?size=1024")

    @classmethod
    async def get_track(cls, ctx: Context, query: str):
        tracks = await NodePool.get_tracks(query, cls=cls)
        if not tracks:
            return None
        return cls(ctx, tracks[0].data)


class Query(commands.Converter):
    async def convert(self, ctx, query: str) -> TTrack | None:
        query = query.strip("<>")

        if "list" in query or "playlist" in query:
            await ctx.send("Not supported.")  # TODO: playlist play command
            return None

        tracks = await TTrack.get_track(ctx, query)
        if tracks is None:
            await ctx.send("No track found.")
            return None

        return tracks[0]


class MusicCog(commands.Cog):
    __cog_name__ = "Music"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        # check if no members (not bot) in vc
        if not member.bot and after.channel is None:
            if not [m for m in before.channel.members if not m.bot]:
                vc: TPlayer = self.get_player(member.guild)
                await vc.disconnect()
                await vc.destroy()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        logger.info(f"Wavelink node {node.id} ready.")

    async def cog_check(self, ctx: Context[BotT]) -> bool:
        if isinstance(ctx.channel, DMChannel):
            await ctx.send("Music is not supported in DMs.")
            return False
        return True

    async def cog_load(self) -> None:
        await self.start_nodes()

    async def start_nodes(self):
        node = Node(uri='http://localhost:2333', password='youshallnotpass')
        await NodePool.connect(client=self.bot, nodes=[node])

    def get_player(self, idf: Union[Context, Guild]) -> TPlayer | None:
        node = NodePool.get_node()
        if isinstance(idf, Context):
            return node.get_player(idf.guild.id)
        elif isinstance(idf, Guild):
            return node.get_player(idf.id)

    @commands.command(name="join", aliases=["connect", 'c', 'j'])
    async def _join(self, ctx: Context):
        vc: TPlayer = ctx.guild.voice_client

        try:
            channel = ctx.author.voice.channel
        except AttributeError:
            return await ctx.send(embed=discord.Embed(
                title="You're not connected to any VC",
                color=EMBED_COLOR
            ), delete_after=5)

        if not vc:
            await channel.connect(cls=TPlayer)
        else:
            await vc.move_to(channel)
        return await ctx.send(embed=discord.Embed(
            title=f"Joined: *{channel.name}*",
            color=EMBED_COLOR
        ))

    @commands.command(name="leave", aliases=['disconnect', 'd', 'l'])
    async def _leave(self, ctx: Context):
        vc: TPlayer = ctx.voice_client

        if vc:
            await ctx.send(embed=discord.Embed(
                title=f"Disconnected: *{vc.channel.name}*",
                color=EMBED_COLOR
            ))
            await vc.disconnect()
            await vc.destroy(ctx.guild)
        else:
            await ctx.send(embed=discord.Embed(
                title="You're not connected to any VC",
                color=EMBED_COLOR
            ), delete_after=5)

    @commands.command(name="play")
    async def _play(self, ctx: Context, *, tracks: Query):
        track: TTrack = tracks
        if track is None:
            return
        return


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
