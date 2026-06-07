from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import ensure_runtime_paths
from app.core.enums import Platform
from app.services.topic_curation import TopicCurationService
from app.storage.base import Base
from app.storage.session import SessionLocal, engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify crawled videos into keep/review/drop without deleting source data."
    )
    parser.add_argument("--platform", default="douyin", choices=[item.value for item in Platform])
    parser.add_argument("--output-dir", default="data/curation/latest")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_runtime_paths()
    Base.metadata.create_all(bind=engine)

    output_dir = Path(args.output_dir)
    with SessionLocal() as db:
        service = TopicCurationService(db)
        summary = service.export(output_dir=output_dir, platform=Platform(args.platform))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
