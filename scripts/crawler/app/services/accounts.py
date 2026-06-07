from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AccountStatus, Platform
from app.services.circuit_breaker import apply_failure, is_available, reset_failures
from app.storage.models import Account


class AccountService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def import_account(self, platform: Platform, label: str, state_file: str) -> Account:
        existing = self.db.scalar(select(Account).where(Account.label == label))
        if existing is not None:
            existing.platform = platform
            existing.login_state_path = str(Path(state_file))
            existing.status = AccountStatus.ACTIVE
            existing.failure_count = 0
            existing.cooldown_until = None
            self.db.commit()
            self.db.refresh(existing)
            return existing
        account = Account(
            platform=platform,
            label=label,
            login_state_path=str(Path(state_file)),
            status=AccountStatus.ACTIVE,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def list_accounts(self) -> list[Account]:
        return list(self.db.scalars(select(Account).order_by(Account.id.asc())))

    def acquire_account(self, platform: Platform) -> Account | None:
        stmt = select(Account).where(Account.platform == platform).order_by(Account.id.asc())
        for account in self.db.scalars(stmt):
            if account.status == AccountStatus.DISABLED:
                continue
            if is_available(account.cooldown_until):
                account.status = AccountStatus.ACTIVE
                self.db.commit()
                return account
        return None

    def mark_success(self, account: Account) -> None:
        state = reset_failures()
        account.failure_count = state.failure_count
        account.cooldown_until = state.cooldown_until
        account.status = AccountStatus.ACTIVE
        account.updated_at = datetime.now(UTC)
        self.db.commit()

    def mark_failure(self, account: Account) -> None:
        state = apply_failure(
            account.failure_count,
            threshold=self.settings.failure_threshold,
            cooldown_seconds=self.settings.cooldown_seconds,
        )
        account.failure_count = state.failure_count
        account.cooldown_until = state.cooldown_until
        account.status = (
            AccountStatus.COOLDOWN if state.cooldown_until else AccountStatus.ACTIVE
        )
        account.updated_at = datetime.now(UTC)
        self.db.commit()
