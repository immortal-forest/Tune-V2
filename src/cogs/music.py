from __future__ import annotations

import re
import os
import yarl
import asyncio
import aiohttp
from typing import Union
from logging import getLogger
from ..utils import paginate_items
from StringProgressBar import progressBar

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands._types import BotT
from discord import Member, VoiceState, DMChannel, Guild, ButtonStyle, Interaction, Message, Reaction, User

from discord.ui import View, Button, button

from wavelink.types.track import Track
from wavelink import (Node, NodePool, Player, Playable, TrackSource, TrackEventPayload,
                      YouTubeTrack, SoundCloudTrack, YouTubePlaylist)

logger = getLogger("discord")
EMBED_COLOR = discord.Color.magenta()
VIDEO_REGEX = r"((?<=(v|V)/)|(?<=be/)|(?<=(\?|\&)v=)|(?<=embed/))([\w-]+)"


class TPlayer(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.autoplay = True
        self.populate = False

    async def destroy(self):
        if self.is_connected():
            await self.disconnect()
        await self._destroy()

    def item_string(self, page: int, items: list[TTrack]):
        start, end, pages = paginate_items(items, page)
        _queue = ''
        for i, track in enumerate(items[start:end], start=start + 1):
            _queue += f"`{i}.` **[{track.title}]({track.uri})**" + "\n"
        return _queue, pages

    def queue_embed(self, page: int = 1):
        items: list[TTrack] = [i for i in self.queue]
        _queue, pages = self.item_string(page, items)
        return (discord.Embed(title="Queue", description=_queue, color=EMBED_COLOR)
                .set_footer(text=f"Page {page}/{pages}"), pages)

    def auto_queue_embed(self, page: int = 1):
        items: list[TTrack] = [i for i in self.auto_queue]
        _queue, pages = self.item_string(page, items)
        return (discord.Embed(title="Auto-Queue", description=_queue, color=EMBED_COLOR)
                .set_footer(text=f"Page {page}/{pages}"), pages)

    def history_embed(self, page: int = 1):
        items: list[TTrack] = [i for i in self.queue.history]
        _queue, pages = self.item_string(page, items)
        return (discord.Embed(title="History", description=_queue, color=EMBED_COLOR)
                .set_footer(text=f"Page {page}/{pages}"), pages)

    async def populate_auto_queue(self, ctx: Context, track: TTrack):
        if not self.populate:
            return

        if track.source == TrackSource.YouTube:
            query = f'https://www.youtube.com/watch?v={track.identifier}&list=RD{track.identifier}'
            recos: YouTubePlaylist = await self.current_node.get_playlist(query=query, cls=YouTubePlaylist)

            ctx.bot.dispatch("populate", ctx=ctx, playlist_name=recos.name, playlist_url=query)

            recos: list[YouTubeTrack] = getattr(recos, "tracks", [])
            queues = set(self.queue) | set(self.auto_queue) | set(self.auto_queue.history) | {track}

            for track_ in recos:
                if track_ in queues:
                    continue
                await self.auto_queue.put_wait(await TTrack.from_track(ctx, track_.data))
            self.auto_queue.shuffle()

            ctx.bot.dispatch("populate_done", message=self.populate_message)

    async def start_player(self):
        if not self.is_playing() and not self.is_paused():
            _track: TTrack = self.queue.get()
            await self.play(_track, populate=self.populate)


class TTrack(Playable):
    # default YouTube
    PREFIX = "ytsearch:"
    PREFIXES = ["ytsearch:", "ytpl:", "ytmsearch:", "scsearch:"]  # TODO: able to change the prefix

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

    @staticmethod
    def parse_duration_fmt(duration):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        days, hours, minutes, seconds = list(map(int, (days, hours, minutes, seconds)))

        fmt = f"{minutes:02}:{seconds:02}"
        if hours > 0:
            fmt = f"{hours:02}:" + fmt
        if days > 0:
            fmt = f"{days:02}:" + fmt

        return fmt

    async def fetch_thumbnail(self):
        if self.source == TrackSource.YouTube:
            self.thumb = await YouTubeTrack.fetch_thumbnail(self)
        elif self.source == TrackSource.SoundCloud:
            self.thumb = ("https://r1.hiclipart.com/path/310/259/692/ksnhqtqg0mddtjejjea3rprovf"
                          "-8f54861ffbc19d4eb264ce3a6740cdd6.png")
        else:
            self.thumb = ("https://cdn.discordapp.com/avatars/980092225960702012/7bd37b51889111531a4ee267d05f48dd.png"
                          "?size=1024")

    @staticmethod
    async def search_tracks(prefix: str, query: str, source: int):
        if source == TrackSource.YouTube:
            tracks = await NodePool.get_tracks(query, cls=YouTubeTrack)
        elif source == TrackSource.SoundCloud:
            tracks = await NodePool.get_tracks(query, cls=SoundCloudTrack)
        else:
            tracks = await NodePool.get_tracks(f"{prefix}{query}", cls=YouTubeTrack)
        return tracks

    @classmethod
    async def create_track(cls, ctx: Context, query: str, source: int):
        tracks = await cls.search_tracks(cls.PREFIX, query, source)

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

    def track_embed(self):
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

    @staticmethod
    async def check_video(_id: str):
        url = "https://img.youtube.com/vi/" + _id + "/mqdefault.jpg"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    return True
                else:
                    return False

    @staticmethod
    def query_source(query: str) -> int:
        if "https://" in query and ("youtube" in query or "youtu.be" in query):
            return TrackSource.YouTube
        elif "soundcloud" in query:
            return TrackSource.SoundCloud
        else:
            return TrackSource.Unknown

    async def parse_query(self, ctx, query: str) -> TTrack | list[TTrack] | None:
        query = re.sub(r'[<>]', '', query)
        check = yarl.URL(query)
        # YouTube or SoundCloud Playlist
        if check.query.get("list") or "sets" in check.parts:
            return await self.parse_playlist(ctx, query)
        return await self.parse_single(ctx, query)

    async def parse_single(self, ctx, query: str) -> TTrack | None:
        source = self.query_source(query)

        if source == TrackSource.YouTube:
            query = re.search(VIDEO_REGEX, query).group() or query

            if await self.check_video(query):
                query = f"https://youtu.be/{query}"
            else:
                await ctx.send("Invalid YouTube video url")
                return None

        track = await TTrack.create_track(ctx, query, source)

        if track is None:
            await ctx.send("No track found.")
            return None

        return track

    async def parse_playlist(self, ctx, query: str) -> list[TTrack] | None:
        await ctx.send("Not supported.")  # TODO: playlist play command
        return None


class MusicEmojis:
    DONE = "✅"
    SKIP = "⏭"
    PLAY = "⏸"
    PAUSE = "▶"
    NEXT = "➡"
    PREVIOUS = "⬅"
    ADDED = "➕"
    REMOVED = "➖"


class MusicUtils:
    SEARCH_OPTIONS = {
        "1️⃣": 0,
        "2️⃣": 1,
        "3️⃣": 2,
        "4️⃣": 3,
        "5️⃣": 4
    }


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

    @button(label=MusicEmojis.PREVIOUS, style=ButtonStyle.red)
    async def prev_button_callback(self, interaction: Interaction, button: Button):
        if self.current == self.pages == 1:
            return await interaction.response.send_message("No previous page!", delete_after=10)
        await interaction.response.defer()
        if self.current == 1:
            self.current = self.pages
        else:
            self.current = self.current - 1
        embed, self.pages = self.func(self.current)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

    @button(label=MusicEmojis.NEXT, style=ButtonStyle.red)
    async def next_button_callback(self, interaction: Interaction, button: Button):
        if self.current == self.pages == 1:
            return await interaction.response.send_message("No next page!", delete_after=10)
        await interaction.response.defer()
        if self.current == self.pages:
            self.current = 1
        else:
            self.current = self.current + 1
        embed, self.pages = self.func(self.current)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)


class MusicCog(commands.Cog, name='Music'):

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
        await track.ctx_.channel.send(embed=track.track_embed())

    @commands.Cog.listener()
    async def on_populate(self, ctx: Context, playlist_name: str, playlist_url: str):
        logger.info(f"Populating: {playlist_url}")
        player: TPlayer = ctx.guild.voice_client
        player.populate_message = await ctx.send(embed=discord.Embed(
            title="Populating auto-queue",
            description=f"**[{playlist_name}]({playlist_url})**",
            color=EMBED_COLOR
        ).set_footer(text="Note: Queue takes precedence over Auto-Queue"))

    @commands.Cog.listener()
    async def on_populate_done(self, message: Message):
        await message.add_reaction(MusicEmojis.DONE)

    async def cog_check(self, ctx: Context[BotT]) -> bool:
        if isinstance(ctx.channel, DMChannel):
            await ctx.send("Music is not supported in DMs.")
            return False
        return True

    async def cog_load(self) -> None:
        await self.start_nodes()

    async def start_nodes(self):
        host = os.environ['LL_HOST']
        port = os.environ['LL_PORT']
        password = os.environ['LL_PASSWORD']
        secure = bool(int(os.getenv("LL_SECURE", False)))  # number: 0 or 1
        node = Node(uri=f'http://{host}:{port}', password=password, secure=secure)
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
            vc.queue.reset()
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

        async with ctx.typing():
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

            await ctx.message.add_reaction(MusicEmojis.ADDED)
            await ctx.send(embed=discord.Embed(
                title="Enqueued a track!",
                description=desc,
                color=EMBED_COLOR
            ))

        await player.populate_auto_queue(ctx, player.current)
        await player.start_player()
        return

    async def search_to_queue(self, ctx: Context, message: Message, tracks, size: int):
        def _check_reaction(rxn: Reaction, user: Member | User):
            return not (not (rxn.emoji in MusicUtils.SEARCH_OPTIONS.keys()) or not (
                        user == ctx.message.author) or not (rxn.message.id == message.id))

        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC. Can't add tracks to the queue.")

        for rxn in list(MusicUtils.SEARCH_OPTIONS.keys())[:size]:
            await message.add_reaction(rxn)

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=_check_reaction)
        except asyncio.Timeout:
            await ctx.send("Reaction timed out!", delete_after=5)
            await message.clear_reactions()
        else:
            track = tracks[:size][MusicUtils.SEARCH_OPTIONS[reaction.emoji]]
            await message.clear_reactions()
            await player.queue.put_wait(await TTrack.from_track(ctx, track.data))
            await ctx.send(embed=discord.Embed(
                title="Enqueued a track!",
                description=f"**[{track.title}]({track.uri})**",
                color=EMBED_COLOR
            ))
            await player.start_player()

    @commands.command(name="search", aliases=['s'])
    async def _search(self, ctx: Context, *, query: str):
        source = Query.query_source(query)
        tracks = await TTrack.search_tracks(TTrack.PREFIX, query, source)
        if not tracks:
            return await ctx.send("No tracks found.")

        _track = ''
        size = min(len(tracks), len(MusicUtils.SEARCH_OPTIONS.keys()))
        for i, track in enumerate(tracks[:size], start=1):
            _track += f"`{i}.` **[{track.title}]({track.uri})**" + "\n"

        message = await ctx.send(embed=discord.Embed(
            title="Tracks found",
            description=_track,
            color=EMBED_COLOR
        ))

        await self.bot.loop.create_task(self.search_to_queue(ctx, message, tracks, size))

    @commands.command(name="history", aliases=['h'])
    async def _history(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.queue.history.is_empty:
            return await ctx.send("Empty history. Play something to see it here.")

        embed, pages = player.history_embed(1)
        view = PaginationUI(pages, player.history_embed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    @commands.command(name="queue", aliases=['q'])
    async def _queue(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")
        if player.queue.is_empty:
            return await ctx.send("Empty queue!")
        embed, pages = player.queue_embed(1)
        view = PaginationUI(pages, player.queue_embed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    @commands.command(name="autoqueue", aliases=['autoq', 'aq', 'aqueue'])
    async def _auto_queue(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.auto_queue.is_empty:
            return await ctx.send("Empty auto-queue!")

        embed, pages = player.auto_queue_embed(1)
        view = PaginationUI(pages, player.auto_queue_embed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    @commands.command(name="populate", aliases=['eaq', 'enableautoqueue'])
    async def _populate(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        player.populate = not player.populate

        return await ctx.send(embed=discord.Embed(
            title=("Enabled" if player.populate else "Disabled") + " Auto-Queue",
            color=EMBED_COLOR
        ))

    @commands.command(name="skip", aliases=['next', 'n'])
    async def _skip(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")
        if not player.is_playing():
            return await ctx.send("Not playing anything at the moment.")

        track: TTrack = player.current
        await player.seek(track.duration + 1)
        await ctx.message.add_reaction(MusicEmojis.SKIP)

    @commands.command(name="volume", aliases=['vol', 'v'])
    async def _volume(self, ctx: Context, value: int = None):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")
        if not player.is_connected():
            return await ctx.send("Not playing anything at the moment.")

        if value is None:
            return await ctx.send(embed=discord.Embed(
                title="Player volume",
                description=f"**`{player.volume}`**",
                color=EMBED_COLOR
            ))

        # supported is 1000 but audio gets distorted
        if value > 200:
            return await ctx.send("Volume must be from 0-200")

        old_volume = player.volume
        await player.set_volume(value)
        vol_increase = ((player.volume - old_volume) / old_volume) * 100
        prefix = "+" if player.volume > old_volume else ""
        return await ctx.send(embed=discord.Embed(
            title="Player volume",
            description=f"**`{player.volume} ({prefix}{vol_increase}%)`**",
            color=EMBED_COLOR
        ))

    @commands.command(name="pause")
    async def _pause(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.current is None or player.is_paused():
            return await ctx.send("Not playing anything at the moment.")
        else:
            await player.pause()
            await ctx.message.add_reaction(MusicEmojis.PAUSE)
            return await ctx.send(embed=discord.Embed(
                title="Paused",
                color=EMBED_COLOR
            ))

    @commands.command(name="resume")
    async def _resume(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.current is None:
            return await ctx.send("Not playing anything at the moment.")
        if player.is_playing():
            return await ctx.send("Player isn't paused!")
        await ctx.message.add_reaction(MusicEmojis.PLAY)
        await player.resume()
        return await ctx.send(embed=discord.Embed(
            title="Resumed",
            color=EMBED_COLOR
        ))

    @commands.command(name="seek")
    async def _seek(self, ctx: Context, position: int = None):
        if position is None:
            return await ctx.send("Player position is required!")

        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if not player.is_playing() or player.is_paused():
            return await ctx.send("Not playing anything at the moment.")

        if position < 0:
            return await ctx.send("Seek value can't be negative.")

        pos = position * 1000  # convert to millisecond
        await player.seek(pos)
        return await ctx.send(embed=discord.Embed(
            title="Player position",
            description=f"**`{TTrack.parse_duration_fmt(position)}`**",
            color=EMBED_COLOR
        ))

    @commands.command(name="nowplaying", aliases=['np', 'current'])
    async def _now_playing(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.current is None:
            return await ctx.send("Not playing anything at the moment.")

        current: TTrack = player.current
        played = int(player.position / 1000)
        embed = current.track_embed()
        embed.insert_field_at(index=1, name="Played", value=TTrack.parse_duration(played), inline=False)
        progress_bar = progressBar.splitBar(int(current.duration / 1000), played, size=12)[0]
        embed.insert_field_at(index=2, name="", value=progress_bar, inline=False)
        return await ctx.send(embed=embed)

    @commands.command(name="shuffle")
    async def _shuffle(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")
        if player.queue.is_empty:
            return await ctx.send("Empty queue.")

        player.queue.shuffle()
        return await ctx.send(embed=discord.Embed(
            title="Shuffled the queue.",
            color=EMBED_COLOR
        ))

    @commands.command(name="loops", aliases=['ls'])
    async def _loop_single(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.current is None:
            return await ctx.send("Not playing anything at the moment.")

        if player.queue.loop_all:
            return await ctx.send("Queue loop is enabled. Disable it to loop a single track.")

        player.queue.loop = not player.queue.loop
        if player.queue.loop:
            track: TTrack = player.current
            await ctx.send(embed=discord.Embed(
                title="Looping track",
                description=f"**[{track.title}]({track.uri})**",
                color=EMBED_COLOR
            ))
        else:
            await ctx.send(embed=discord.Embed(
                title="Disabled single track looping",
                color=EMBED_COLOR
            ))

    @commands.command(name="loopq", aliases=['lq', 'loopall', 'la'])
    async def _loop_all(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.current is None:
            return await ctx.send("Not playing anything at the moment.")

        if player.queue.loop:
            return await ctx.send("Single track loop is enabled. Disable it to loop the queue.")

        player.queue.loop_all = not player.queue.loop_all
        if player.queue.loop_all:
            await ctx.send(embed=discord.Embed(
                title="Looping the queue",
                color=EMBED_COLOR
            ).set_footer(text="Note: Tracks will be played from history if queue is empty."))
        else:
            await ctx.send(embed=discord.Embed(
                title="Disabled queue looping",
                color=EMBED_COLOR
            ))

    @commands.command(name="clear")
    async def _clear(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.queue.is_empty:
            return await ctx.send("Empty queue.")

        player.queue.clear()
        return await ctx.send(embed=discord.Embed(
            title="Cleared the queue",
            color=EMBED_COLOR
        ))

    @commands.command(name="remove", aliases=['rm'])
    async def _remove(self, ctx: Context, index: int = None):
        if index is None:
            return await ctx.send("Track's index is needed.")

        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        if player.queue.is_empty:
            return await ctx.send("Empty queue.")

        _index = index - 1
        if _index < 0:
            return await ctx.send("Index can't be `0`.")
        if _index > player.queue.count:
            return await ctx.send(f"No track at index `{index}`.")

        track: TTrack = player.queue[_index]
        del player.queue[_index]
        return await ctx.send(embed=discord.Embed(
            title="Removed a track from the queue",
            description=f"**[{track.title}]({track.uri})**",
            color=EMBED_COLOR
        ))

    @commands.command(name="playerstatus", aliases=['ps'])
    async def _player_status(self, ctx: Context):
        player: TPlayer = ctx.guild.voice_client
        if not player:
            return await ctx.send("Not connected to a VC.")

        queue_len = len(player.queue)
        history_len = len(player.queue.history)
        ping = player.ping
        vol = player.volume
        if player.is_playing():
            status = "**Playing**"
        elif player.is_paused():
            status = "**Paused**"
        else:
            status = "**Idling**"
        current: TTrack = player.current or None
        embed = (discord.Embed(
            title="Player Stats",
            color=EMBED_COLOR
        )
                 .add_field(name="Status", value=status)
                 .add_field(name="Volume", value=vol)
                 .add_field(name="", value="", inline=False)
                 .add_field(name="In-Queue", value=queue_len)
                 .add_field(name="History", value=history_len)
                 .add_field(name="Latency", value=f"{ping:.2f} ms", inline=False))
        if current is not None:
            embed.insert_field_at(0, name="Current", value=f"[{current.title}]({current.uri})", inline=False)
        return await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
