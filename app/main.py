import asyncio
import logging

from .bot import SecretaryBot
from .config import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(SecretaryBot(load_settings()).run())


if __name__ == "__main__":
    main()
