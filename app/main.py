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
        "reminder_options=%s database=%s",
        len(settings.admin_ids),
        len(settings.targets),
        settings.timezone_name,
        settings.scheduler_interval_seconds,
        settings.reminder_options_minutes,
        settings.database_path,
    )
    log.info(
        "AI topic configuration: enabled=%s target=%s questions=%s "
        "vocabulary=%s grammar=%s",
        bool(settings.deepseek_api_key),
        settings.ai_topics.target.key if settings.ai_topics.target else None,
        settings.ai_topics.question_count,
        settings.ai_topics.vocabulary_count,
        settings.ai_topics.grammar_count,
    )
    asyncio.run(SecretaryBot(settings).run())


if __name__ == "__main__":
    main()
