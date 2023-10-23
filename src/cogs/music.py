import re
import yarl
import aiohttp
from typing import Union
from logging import getLogger
from ..utils import paginate_items

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands._types import BotT
from discord import Member, VoiceState, DMChannel, Guild, ButtonStyle, Interaction

from discord.ui import View, Button, button

from wavelink.types.track import Track
from wavelink import (Node, NodePool, Player, Playable, TrackSource, TrackEventPayload,
                      YouTubeTrack, SoundCloudTrack)

logger = getLogger("discord")
EMBED_COLOR = discord.Color.magenta()
VIDEO_REGEX = r"((?<=(v|V)/)|(?<=be/)|(?<=(\?|\&)v=)|(?<=embed/))([\w-]+)"


class TPlayer(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.autoplay = True

    async def destroy(self):
        if self.is_connected():
            await self.disconnect()
        await self._destroy()

    def queue_embed(self, page: int = 1):
        items: list[TTrack] = [i for i in self.queue]
        start, end, pages = paginate_items(items, page)
        _queue = ''
        for i, track in enumerate(items[start:end], start=start + 1):
            _queue += f"`{i}.` **[{track.title}]({track.uri})**" + "\n"
        return (discord.Embed(title="Queue", description=_queue, color=EMBED_COLOR)
                .set_footer(text=f"Page {page}/{pages}"), pages)


class TTrack(Playable):
    # default YouTube
    PREFIX = "ytsearch:"
    PREFIXES = ["ytsearch:", "ytpl:", "ytmsearch:", "scsearch:"]

    def __init__(self, data: Track):
        super().__init__(data)
        self.thumb = None
        self.parsed_duration: str = self.parse_duration(self.length / 1000)
        self.ctx_: Context | None = None

    @staticmethod
    def parse_duration(duration):
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
    async def create_track(cls, ctx: Context, query: str, source: int):
        if source == TrackSource.YouTube:
            tracks = await NodePool.get_tracks(query, cls=YouTubeTrack)
        elif source == TrackSource.SoundCloud:
            tracks = await NodePool.get_tracks(query, cls=SoundCloudTrack)
        else:
            tracks = await NodePool.get_tracks(f"{cls.PREFIX}{query}", cls=cls)

        if not tracks:
            return None
        track = cls(tracks[0].data)
        track.ctx_ = ctx
        await track.fetch_thumbnail()
        return track

    @classmethod
    async def from_track(cls, ctx: Context, data: Track):
        _cls = cls(data)
        await _cls.fetch_thumbnail()
        _cls.ctx_ = ctx
        return _cls

    async def track_embed(self):
        return (discord.Embed(
            title="Now Playing!",
            description=f"[{self.title}]({self.uri})",
            color=discord.Color.blurple()
        )
                .add_field(name="Duration", value=self.parsed_duration, inline=False)
                .add_field(name="Requested by", value=self.ctx_.author.mention, inline=False)
                .add_field(name="Uploader", value=self.author)
                .set_thumbnail(url=self.thumb))


class Query:

    async def check_video(self, _id: str):
        url = "https://img.youtube.com/vi/" + _id + "/mqdefault.jpg"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    return True
                else:
                    return False

    async def parse_query(self, ctx, query: str) -> TTrack | list[TTrack] | None:
        query = re.sub(r'[<>]', '', query)
        check = yarl.URL(query)
        # YouTube or SoundCloud Playlist
        if check.query.get("list") or "sets" in check.parts:
            return await self.parse_playlist(ctx, query)
        return await self.parse_single(ctx, query)

    async def parse_single(self, ctx, query: str) -> TTrack | None:
        if "https://" in query and ("youtube" in query or "youtu.be" in query):
            query = re.search(VIDEO_REGEX, query).group() or query

            if await self.check_video(query):
                query = f"https://youtu.be/{query}"
            else:
                await ctx.send("Invalid YouTube video url")
                return None

            track = await TTrack.create_track(ctx, query, TrackSource.YouTube)

        elif "soundcloud" in query:
            track = await TTrack.create_track(ctx, query, TrackSource.SoundCloud)

        else:  # default use YouTube
            track = await TTrack.create_track(ctx, query, TrackSource.Unknown)

        if track is None:
            await ctx.send("No track found.")
            return None

        return track

    async def parse_playlist(self, ctx, query: str) -> list[TTrack] | None:
        await ctx.send("Not supported.")  # TODO: playlist play command
        return None


class PaginationUI(View):
    def __init__(self, pages: int, func):
        super().__init__(timeout=60 * 2)
        self.current = 1
        self.pages = pages
        self.func = func

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @button(label="<-", style=ButtonStyle.red)
    async def prev_button_callback(self, interaction: Interaction, button: Button):
        if self.current == self.pages:
            return await interaction.response.send_message("No previous page!", delete_after=10)
        await interaction.response.defer()
        if self.current == 1:
            self.current = self.pages
        else:
            self.current = self.current - 1
        embed, self.pages = self.func(self.current)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

    @button(label="->", style=ButtonStyle.red)
    async def next_button_callback(self, interaction: Interaction, button: Button):
        if self.current == self.pages:
            return await interaction.response.send_message("No next page!", delete_after=10)
        await interaction.response.defer()
        if self.current == self.pages:
            self.current = 1
        else:
            self.current = self.current + 1
        embed, self.pages = self.func(self.current)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)


class MusicEmojis:
    SKIP = "⏭"
    PLAY = "⏸"
    PAUSE = "▶"
    NEXT = "➡"
    PREVIOUS = "⬅"


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
                if not vc:
                    return
                await vc.disconnect()
                await vc.destroy()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        logger.info(f"Wavelink node {node.id} ready.")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackEventPayload):
        track: TTrack = payload.original
        await track.ctx_.channel.send(embed=await track.track_embed())

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
        elif vc.channel == channel:
            return await ctx.send("Bot is already in VC.", delete_after=5)
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
            await vc.destroy()
        else:
            await ctx.send(embed=discord.Embed(
                title="You're not connected to any VC",
                color=EMBED_COLOR
            ), delete_after=5)

    @commands.command(name="play")
    async def _play(self, ctx: Context, *, query: str):
        if not ctx.guild.voice_client:
            await ctx.invoke(self._join)

        player: TPlayer = ctx.guild.voice_client

        if not player:
            return

        tracks = await Query().parse_query(ctx, query)
        if isinstance(tracks, list):
            for track in tracks:
                await player.queue.put_wait(track)
            desc = f"**Playlist {len(tracks)}**"  # TODO: playlist name from TPlaylistTrack
        elif isinstance(tracks, TTrack):
            await player.queue.put_wait(tracks)
            desc = f"**[{tracks.title}]({tracks.uri})**"
        else:
            return

        await ctx.send(embed=discord.Embed(
            title="Enqueued a track!",
            description=desc,
            color=EMBED_COLOR
        ))

        if not player.is_playing():
            await player.play(player.queue.get(), populate=True)  # TODO: fix populate not working for TTrack
        return

    @commands.command(name="queue", aliases=['q'])
    async def _queue(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if player.queue.is_empty:
            return await ctx.send("Empty queue!")
        embed, pages = player.queue_embed(1)
        view = PaginationUI(pages, player.queue_embed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    @commands.command(name="skip", aliases=['next', 'n'])
    async def _skip(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player.is_playing():
            return await ctx.send("Not playing anything at the moment.")
        track: TTrack = player.current
        await player.seek(track.duration + 1)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
