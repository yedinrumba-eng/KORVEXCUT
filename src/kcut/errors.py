"""Exception hierarchy. Each subclass fixes the process exit code (spec 0.5)."""


class KcutError(Exception):
    """Base class of every expected failure; carries the exit code and a Spanish message."""

    exit_code: int = 10

    def __init__(self, message_es: str) -> None:
        super().__init__(message_es)
        self.message_es = message_es


class CheckFailed(KcutError):
    """A check reported problems: doctor, edl check, graphics check, QA fail."""

    exit_code = 1


class UsageError(KcutError):
    """Invalid command-line arguments."""

    exit_code = 2


class ProjectError(KcutError):
    """Missing project, invalid config, bad path, missing file, malformed JSON, locked target."""

    exit_code = 3


class ToolError(KcutError):
    """ffmpeg, ffprobe or Chromium finished with an error."""

    exit_code = 4


class GateError(KcutError):
    """Strategy not approved or resource not approved in the manifest."""

    exit_code = 5


class LockedError(KcutError):
    """Another process is rendering the same output."""

    exit_code = 6


class MissingDependency(KcutError):
    """ffmpeg, a Whisper model or Chromium is not available at run time."""

    exit_code = 7


class InternalError(KcutError):
    """Unexpected exception; the traceback goes to the log, the user gets a short message."""

    exit_code = 10
