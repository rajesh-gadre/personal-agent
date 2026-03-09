"""Notification adapters -- stub for future implementation."""


class NotificationAdapter:
    def send(self, message: str, recipient: str | None = None) -> None:
        raise NotImplementedError
