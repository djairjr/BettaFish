# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


from __future__ import annotations


import sys
from enum import Enum
from types import SimpleNamespace
from typing import Iterable, Optional, Sequence, Type, TypeVar

import typer
from typing_extensions import Annotated

import config
from tools.utils import str2bool


EnumT = TypeVar("EnumT", bound=Enum)


class PlatformEnum(str, Enum):
    """Enumeration of supported media platforms"""

    XHS = "xhs"
    DOUYIN = "dy"
    KUAISHOU = "ks"
    BILIBILI = "bili"
    WEIBO = "wb"
    TIEBA = "tieba"
    ZHIHU = "zhihu"


class LoginTypeEnum(str, Enum):
    """Login method enumeration"""

    QRCODE = "qrcode"
    PHONE = "phone"
    COOKIE = "cookie"


class CrawlerTypeEnum(str, Enum):
    """Crawler type enum"""

    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"


class SaveDataOptionEnum(str, Enum):
    """Data storage method enumeration"""

    CSV = "csv"
    DB = "db"
    JSON = "json"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class InitDbOptionEnum(str, Enum):
    """Database initialization options"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


def _to_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str2bool(value)


def _coerce_enum(
    enum_cls: Type[EnumT],
    value: EnumT | str,
    default: EnumT,
) -> EnumT:
    """Safely convert a raw config value to an enum member."""

    if isinstance(value, enum_cls):
        return value

    try:
        return enum_cls(value)
    except ValueError:
        typer.secho(
            f"⚠️ The configuration value '{value}' is not within the range supported by {enum_cls.__name__} and has fallen back to the default value '{default.value}'.",
            fg=typer.colors.YELLOW,
        )
        return default


def _normalize_argv(argv: Optional[Sequence[str]]) -> Iterable[str]:
    if argv is None:
        return list(sys.argv[1:])
    return list(argv)


def _inject_init_db_default(args: Sequence[str]) -> list[str]:
    """Ensure bare --init_db defaults to sqlite for backward compatibility."""

    normalized: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        normalized.append(arg)

        if arg == "--init_db":
            next_arg = args[i + 1] if i + 1 < len(args) else None
            if not next_arg or next_arg.startswith("-"):
                normalized.append(InitDbOptionEnum.SQLITE.value)
        i += 1

    return normalized


async def parse_cmd(argv: Optional[Sequence[str]] = None):
    """Use Typer to parse command line arguments."""

    app = typer.Typer(add_completion=False)

    @app.callback(invoke_without_command=True)
    def main(
        platform: Annotated[
            PlatformEnum,
            typer.Option(
                "--platform",
                help="Media platform selection (xhs=Little Red Book | dy=Douyin | ks=Kuaishou | bili=Bilibili | wb=Weibo | tieba=Baidu Tieba | zhihu=Zhihu)",
                rich_help_panel="Basic configuration",
            ),
        ] = _coerce_enum(PlatformEnum, config.PLATFORM, PlatformEnum.XHS),
        lt: Annotated[
            LoginTypeEnum,
            typer.Option(
                "--lt",
                help="Login method (qrcode=QR code | phone=mobile phone number | cookie=Cookie)",
                rich_help_panel="Account configuration",
            ),
        ] = _coerce_enum(LoginTypeEnum, config.LOGIN_TYPE, LoginTypeEnum.QRCODE),
        crawler_type: Annotated[
            CrawlerTypeEnum,
            typer.Option(
                "--type",
                help="Crawling type (search=search | detail=details | creator=creator)",
                rich_help_panel="Basic configuration",
            ),
        ] = _coerce_enum(CrawlerTypeEnum, config.CRAWLER_TYPE, CrawlerTypeEnum.SEARCH),
        start: Annotated[
            int,
            typer.Option(
                "--start",
                help="Starting page number",
                rich_help_panel="Basic configuration",
            ),
        ] = config.START_PAGE,
        keywords: Annotated[
            str,
            typer.Option(
                "--keywords",
                help="Please enter keywords, separate multiple keywords with commas",
                rich_help_panel="Basic configuration",
            ),
        ] = config.KEYWORDS,
        get_comment: Annotated[
            str,
            typer.Option(
                "--get_comment",
                help="Whether to crawl first-level comments, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Comment configuration",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_COMMENTS),
        get_sub_comment: Annotated[
            str,
            typer.Option(
                "--get_sub_comment",
                help="Whether to crawl secondary comments, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Comment configuration",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_SUB_COMMENTS),
        save_data_option: Annotated[
            SaveDataOptionEnum,
            typer.Option(
                "--save_data_option",
                help="Data storage method (csv=CSV file | db=MySQL database | json=JSON file | sqlite=SQLite database | postgresql=PostgreSQL database)",
                rich_help_panel="Storage configuration",
            ),
        ] = _coerce_enum(
            SaveDataOptionEnum, config.SAVE_DATA_OPTION, SaveDataOptionEnum.JSON
        ),
        init_db: Annotated[
            Optional[InitDbOptionEnum],
            typer.Option(
                "--init_db",
                help="Initialize database table structure (sqlite | mysql | postgresql)",
                rich_help_panel="Storage configuration",
            ),
        ] = None,
        cookies: Annotated[
            str,
            typer.Option(
                "--cookies",
                help="Cookie value used by cookie login method",
                rich_help_panel="Account configuration",
            ),
        ] = config.COOKIES,
    ) -> SimpleNamespace:
        """MediaCrawler command line entry"""

        enable_comment = _to_bool(get_comment)
        enable_sub_comment = _to_bool(get_sub_comment)
        init_db_value = init_db.value if init_db else None

        # override global config
        config.PLATFORM = platform.value
        config.LOGIN_TYPE = lt.value
        config.CRAWLER_TYPE = crawler_type.value
        config.START_PAGE = start
        config.KEYWORDS = keywords
        config.ENABLE_GET_COMMENTS = enable_comment
        config.ENABLE_GET_SUB_COMMENTS = enable_sub_comment
        config.SAVE_DATA_OPTION = save_data_option.value
        config.COOKIES = cookies

        return SimpleNamespace(
            platform=config.PLATFORM,
            lt=config.LOGIN_TYPE,
            type=config.CRAWLER_TYPE,
            start=config.START_PAGE,
            keywords=config.KEYWORDS,
            get_comment=config.ENABLE_GET_COMMENTS,
            get_sub_comment=config.ENABLE_GET_SUB_COMMENTS,
            save_data_option=config.SAVE_DATA_OPTION,
            init_db=init_db_value,
            cookies=config.COOKIES,
        )

    command = typer.main.get_command(app)

    cli_args = _normalize_argv(argv)
    cli_args = _inject_init_db_default(cli_args)

    try:
        result = command.main(args=cli_args, standalone_mode=False)
        if isinstance(result, int):  # help/options handled by Typer; propagate exit code
            raise SystemExit(result)
        return result
    except typer.Exit as exc:  # pragma: no cover - CLI exit paths
        raise SystemExit(exc.exit_code) from exc
