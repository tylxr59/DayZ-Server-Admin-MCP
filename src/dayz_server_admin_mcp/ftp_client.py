"""Compatibility imports for the original FTP-only module name."""

from .remote_client import DayZFtpClient, FtpError, RemoteEntry, WriteDisabledError

__all__ = ["DayZFtpClient", "FtpError", "RemoteEntry", "WriteDisabledError"]
