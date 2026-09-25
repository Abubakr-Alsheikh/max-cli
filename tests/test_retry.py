from typing import List
from unittest.mock import patch

import pytest

from max_cli.common.retry import retry


class Flaky:
    """Callable that raises the queued exceptions, then returns 'ok'."""

    def __init__(self, errors: List[Exception]) -> None:
        self.errors = list(errors)
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


@pytest.fixture
def mock_sleep():
    with patch("max_cli.common.retry.time.sleep") as sleep:
        yield sleep


def test_success_on_first_try_does_not_sleep(mock_sleep):
    flaky = Flaky([])

    assert retry()(flaky)() == "ok"
    assert flaky.call_count == 1
    mock_sleep.assert_not_called()


def test_retries_until_success(mock_sleep):
    flaky = Flaky([OSError("1"), OSError("2")])

    assert retry(max_attempts=3)(flaky)() == "ok"
    assert flaky.call_count == 3
    assert mock_sleep.call_count == 2


def test_exponential_backoff_delays(mock_sleep):
    flaky = Flaky([OSError()] * 4)

    retry(max_attempts=5, delay=0.5, backoff=3.0)(flaky)()

    assert [call.args[0] for call in mock_sleep.call_args_list] == [
        0.5,
        1.5,
        4.5,
        13.5,
    ]


def test_reraises_last_exception_after_max_attempts(mock_sleep):
    first, second, last = OSError("first"), OSError("second"), OSError("last")
    flaky = Flaky([first, second, last])

    with pytest.raises(OSError) as raised:
        retry(max_attempts=3)(flaky)()

    assert raised.value is last
    assert flaky.call_count == 3
    assert mock_sleep.call_count == 2


def test_unlisted_exception_is_not_retried(mock_sleep):
    flaky = Flaky([KeyError("boom")])

    with pytest.raises(KeyError):
        retry(max_attempts=5, exceptions=(OSError,))(flaky)()

    assert flaky.call_count == 1
    mock_sleep.assert_not_called()


def test_listed_exception_subclass_is_retried(mock_sleep):
    flaky = Flaky([FileNotFoundError(), ConnectionError()])

    result = retry(max_attempts=3, exceptions=(OSError,))(flaky)()

    assert result == "ok"
    assert flaky.call_count == 3


def test_single_attempt_never_sleeps(mock_sleep):
    flaky = Flaky([OSError("once")])

    with pytest.raises(OSError, match="once"):
        retry(max_attempts=1)(flaky)()

    mock_sleep.assert_not_called()


def test_passes_arguments_and_preserves_metadata(mock_sleep):
    @retry()
    def add(left: int, right: int = 0) -> int:
        """Add two numbers."""
        return left + right

    assert add(2, right=3) == 5
    assert add.__name__ == "add"
    assert add.__doc__ == "Add two numbers."


def test_logs_warning_per_retry_and_error_on_give_up(mock_sleep, caplog):
    flaky = Flaky([OSError("a"), OSError("b")])

    with caplog.at_level("WARNING", logger="max_cli.common.retry"):
        with pytest.raises(OSError):
            retry(max_attempts=2, delay=1.0)(flaky)()

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Attempt 1/2 failed: a. Retrying in 1.0s...",
        "Failed after 2 attempts: b",
    ]
