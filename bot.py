import os
from dotenv import load_dotenv
from src import Tune, discord_logger


def main():
    load_dotenv()
    discord_logger()
    bot = Tune()
    bot.tune()


if __name__ == "__main__":
    main()
