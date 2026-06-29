"""Provider environment-variable inventory and redaction tests."""

from pathlib import Path

import pytest

from galaxy_merge.app.lifecycle import PROVIDER_ENV_VARS
from galaxy_merge.safety.credential_policy import CredentialPolicy

pytestmark = [pytest.mark.unit]


def test_export_provider_env_vars_are_known_to_doctor() -> None:
    # Given: the OpenCode export includes Kimi, NVIDIA NIM, and Ollama Cloud.
    expected = {"KIMI_API_KEY", "NVIDIA_API_KEY", "OLLAMA_API_KEY"}

    # When: doctor/boot provider inventory is consulted.
    known = set(PROVIDER_ENV_VARS)

    # Then: those provider key names are first-class runtime config inputs.
    assert expected.issubset(known)


def test_export_provider_env_var_assignments_are_redacted() -> None:
    # Given: provider env assignments appear in tool output or logs.
    policy = CredentialPolicy(Path("/tmp"))
    text = "NVIDIA_API_KEY=value KIMI_API_KEY=value OLLAMA_API_KEY=value"

    # When: credential policy redacts the text.
    redacted = policy.redact(text)

    # Then: every assignment is preserved by name but value-redacted.
    assert "NVIDIA_API_KEY=***REDACTED***" in redacted
    assert "KIMI_API_KEY=***REDACTED***" in redacted
    assert "OLLAMA_API_KEY=***REDACTED***" in redacted
