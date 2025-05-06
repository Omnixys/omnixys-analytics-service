"""MainApp."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse
from loguru import logger

from kpi.config import dev, env
from kpi.config.dev.db_populate_router import router as db_populate_router
from kpi.config.dev.db_populate import db_populate
from kpi.error.exceptions import NotAllowedError, NotFoundError, VersionOutdatedError
from kpi.graphql.schema import graphql_router
from kpi.kafka.producer import KafkaProducerService
from kpi.repositories.session import dispose_connection_pool
from kpi.router import health_router, shutdown_router, export_router

from .banner import banner

__all__ = [
    "authorization_error_handler",
    "email_exists_error_handler",
    "login_error_handler",
    "not_allowed_error_handler",
    "not_found_error_handler",
    "username_exists_error_handler",
    "version_outdated_error_handler",
]


TEXT_PLAIN: Final = "text/plain"
kafka_producer = KafkaProducerService()

# --------------------------------------------------------------------------------------
# S t a r t u p   u n d   S h u t d o w n
# --------------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: RUF029
    """Startup/Shutdown-Logik: MongoDB, Kafka, Banner."""
    db_populate()
    await kafka_producer.start()
    banner(app.routes)
    yield
    await kafka_producer.stop()
    logger.info("Der Server wird heruntergefahren")
    dispose_connection_pool()

if env.APP_ENV == "development":
    app: Final = FastAPI(lifespan=lifespan, debug=True)
else:
    app: Final = FastAPI(lifespan=lifespan)


# --------------------------------------------------------------------------------------
# R E S T
# --------------------------------------------------------------------------------------
app.include_router(export_router, prefix="/export")
app.include_router(health_router, prefix="/health")
app.include_router(shutdown_router, prefix="/admin")
if dev:
    app.include_router(db_populate_router, prefix="/dev")


# --------------------------------------------------------------------------------------
# G r a p h Q L
# --------------------------------------------------------------------------------------
app.include_router(graphql_router, prefix="/graphql")

# --------------------------------------------------------------------------------------
# F a v i c o n
# --------------------------------------------------------------------------------------
@app.get("/favicon.ico")
def favicon() -> FileResponse:
    """facicon.ico ermitteln.

    :return: Response-Objekt mit favicon.ico
    :rtype: FileResponse
    """
    src_path: Final = Path("src")
    file_name: Final = "favicon.ico"
    favicon_path: Final = Path("kpi") / "static" / file_name
    file_path: Final = src_path / favicon_path if src_path.is_dir() else favicon_path
    logger.debug("file_path={}", file_path)
    return FileResponse(
        path=file_path,
        headers={"Content-Disposition": f"attachment; filename={file_name}"},
    )


# --------------------------------------------------------------------------------------
# E x c e p t i o n   H a n d l e r
# --------------------------------------------------------------------------------------
@app.exception_handler(NotFoundError)
def not_found_error_handler(_request: Request, _err: NotFoundError) -> Response:
    """Errorhandler für NotFoundError.

    :param _err: NotFoundError aus der Geschäftslogik
    :return: Response mit Statuscode 404
    :rtype: Response
    """
    return Response(status_code=status.HTTP_404_NOT_FOUND, media_type=TEXT_PLAIN)


@app.exception_handler(NotAllowedError)
def not_allowed_error_handler(_request: Request, _err: NotAllowedError) -> Response:
    """Errorhandler für NotAllowedError.

    :param _err: NotAllowedError vom Überprüfen der erforderlichen Rollen
    :return: Response mit Statuscode 401
    :rtype: Response
    """
    return Response(status_code=status.HTTP_401_UNAUTHORIZED, media_type=TEXT_PLAIN)


@app.exception_handler(VersionOutdatedError)
def version_outdated_error_handler(
    _request: Request,
    _err: VersionOutdatedError,
) -> Response:
    """Exception-Handling für VersionOutdatedError.

    :param _err: Exception, falls die Versionsnummer zum Aktualisieren veraltet ist
    :return: Response mit Statuscode 412
    :rtype: Response
    """
    return Response(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        media_type="application/json",
    )
