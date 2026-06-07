from __future__ import annotations

import argparse
from pathlib import Path

from src.config import load_config
from src.pipeline import VisualCodingPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qwen 视觉编码程序")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument(
        "--stage",
        default="all",
        choices=["all", "visual", "export"],
        help="运行阶段：all / visual / export",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_api_key = args.stage in {"all", "visual"}
    config = load_config(Path(args.config).resolve(), require_api_key=require_api_key)
    pipeline = VisualCodingPipeline(config)
    pipeline.run(stage=args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

