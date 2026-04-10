from __future__ import annotations


class AgentCodexError(RuntimeError):
    """Base exception for the Agent_Codex vNext runtime."""


class ConfigError(AgentCodexError):
    """Raised when required configuration is missing or inconsistent."""


class ApiError(AgentCodexError):
    """Raised when an external API call fails."""


class TaskError(AgentCodexError):
    """Raised when task execution or orchestration fails."""


class MemoryStoreError(AgentCodexError):
    """Raised when the memory subsystem cannot read or persist state."""


class StorageError(AgentCodexError):
    """Raised when filesystem-backed state cannot be written safely."""
