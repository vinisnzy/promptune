from types import SimpleNamespace

import pytest

from promptune.modules.agent_run.processor import _is_transient


class ProviderError(Exception):
    def __init__(self, status_code: int | None = None, response=None) -> None:
        super().__init__("provider error")
        self.status_code = status_code
        self.response = response


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        ConnectionError(),
        type("RateLimitError", (Exception,), {})(),
        ProviderError(status_code=429),
        ProviderError(status_code=503),
        ProviderError(response=SimpleNamespace(status_code=500)),
    ],
)
def test_should_treat_error_as_transient(error: Exception) -> None:
    assert _is_transient(error)


@pytest.mark.parametrize(
    "error",
    [
        ValueError(),
        ProviderError(status_code=400),
        ProviderError(status_code=401),
        ProviderError(response=SimpleNamespace(status_code=404)),
    ],
)
def test_should_treat_error_as_permanent(error: Exception) -> None:
    assert not _is_transient(error)
