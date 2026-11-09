from __future__ import annotations

import argparse
import asyncio
import json
import os

from projects.mind.test_backend.config import get_feishu_config
from projects.mind.test_backend.service.task.feishu_notify_service import (
    FeishuNotifyConfig,
    lookup_feishu_user_ids,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lookup Feishu user IDs by email or mobile."
    )
    parser.add_argument("--email", action="append", default=[], help="Feishu user email")
    parser.add_argument(
        "--mobile",
        action="append",
        default=[],
        help="Feishu user mobile number, for example 13800138000",
    )
    parser.add_argument(
        "--user-id-type",
        default="open_id",
        choices=["open_id", "user_id", "union_id"],
        help="ID type used by Feishu query parameter. Default: open_id",
    )
    return parser


def _get_env_config() -> FeishuNotifyConfig:
    feishu_config = get_feishu_config()
    app_id = feishu_config.app_id
    app_secret = feishu_config.app_secret
    if not app_id or not app_secret:
        raise SystemExit(
            "Missing FEISHU_APP_ID or FEISHU_APP_SECRET in environment."
        )

    return FeishuNotifyConfig(
        app_id=app_id,
        app_secret=app_secret,
        receive_id="_lookup_only_",
    )


async def _main() -> None:
    args = _build_parser().parse_args()
    if not args.email and not args.mobile:
        raise SystemExit("Please provide --email or --mobile.")

    data = await lookup_feishu_user_ids(
        _get_env_config(),
        emails=args.email,
        mobiles=args.mobile,
        user_id_type=args.user_id_type,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
