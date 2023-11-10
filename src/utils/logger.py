import logging
from logging import handlers


def discord_logger(file_path: str = "./logs/discord.log", log_level: int | str = logging.INFO):
    discordLogger = logging.getLogger("discord")
    discordLogger.propagate = False
    discordLogger.setLevel(log_level)
    logging.getLogger("discord.http").setLevel(log_level)

    handler = handlers.RotatingFileHandler(
        filename=file_path,
        encoding='utf-8',
        maxBytes=1024 * 1024 * 10,  # 10 Mib
        backupCount=5
    )
    datetime_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', datetime_format, style='{')
    handler.setFormatter(formatter)
    discordLogger.addHandler(handler)
