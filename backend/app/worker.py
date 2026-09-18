from app.logging import configure_logging, get_logger


def main() -> None:
    configure_logging()
    logger = get_logger(service="worker")
    import redis
    from rq import Worker

    from app.config import get_settings

    settings = get_settings()
    logger.info("worker_starting", queue=settings.rq_queue_name)
    connection = redis.from_url(settings.redis_url)
    Worker([settings.rq_queue_name], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
