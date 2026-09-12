"""Operations database DSN construction with explicit configuration inputs."""

from collections.abc import Callable
from typing import Any, Optional


def build_ops_dsn(
    mysql_dsn: Optional[str],
    ops_mysql_user: str,
    ops_mysql_password: str,
    ops_mysql_database: Optional[str],
    mysql_hostname: str,
    mysql_port: int,
    *,
    create_url: Callable[..., Any],
) -> Optional[str]:
    """Build the operations database DSN following configured precedence."""
    if mysql_dsn:
        return mysql_dsn
    if ops_mysql_user and ops_mysql_password and ops_mysql_database:
        return create_url(
            "mysql+pymysql",
            username=ops_mysql_user,
            password=ops_mysql_password,
            host=mysql_hostname,
            port=mysql_port,
            database=ops_mysql_database,
        ).render_as_string(hide_password=False)
    return None
