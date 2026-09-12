"""Guacamole DSN construction with explicit configuration dependencies."""

from collections.abc import Callable
from typing import Any, Optional


def build_guacamole_dsn(
    guacamole_dsn: Optional[str],
    guacamole_user: str,
    guacamole_password: str,
    guacamole_database: Optional[str],
    mysql_dsn: Optional[str],
    mysql_hostname: str,
    mysql_port: int,
    *,
    create_url: Callable[..., Any],
    parse_url: Callable[[str], Any],
    logger: Any,
) -> Optional[str]:
    """Build the Guacamole DSN following the configured source precedence."""
    if guacamole_dsn:
        return guacamole_dsn
    if guacamole_user and guacamole_password and guacamole_database:
        return create_url(
            "mysql+pymysql",
            username=guacamole_user,
            password=guacamole_password,
            host=mysql_hostname,
            port=mysql_port,
            database=guacamole_database,
        ).render_as_string(hide_password=False)
    if not mysql_dsn or not guacamole_database:
        return None
    try:
        return str(parse_url(mysql_dsn).set(database=guacamole_database))
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Unable to derive Guacamole DSN from MYSQL_DSN: %s", exc)
        return None
