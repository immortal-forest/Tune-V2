import os
from dotenv import load_dotenv
from src import Tune, discord_logger


def main():
    load_dotenv()
    discord_logger(os.environ['LOG_PATH'], int(os.environ['LOG_LEVEL']))
    bot = Tune()
    bot.tune()


if __name__ == "__main__":
    main()
