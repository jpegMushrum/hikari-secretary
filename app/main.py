import asyncio
import logging

from .bot import SecretaryBot
from .config import load_settings


log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    log.info(
        "Configuration loaded: admins=%s targets=%s timezone=%s scheduler_interval=%ss "
        "event_reminder=%sh database=%s",
        len(settings.admin_ids),
        len(settings.targets),
        settings.timezone_name,
        settings.scheduler_interval_seconds,
        settings.event_reminder_hours,
        settings.database_path,
    )
    asyncio.run(SecretaryBot(settings).run())


if __name__ == "__main__":
    main()
