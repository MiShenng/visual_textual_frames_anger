class AntiCrawlDetectedError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        status_code: int | None = None,
        marker: str | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.status_code = status_code
        self.marker = marker
