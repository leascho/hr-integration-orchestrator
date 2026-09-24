from app.orchestration.retry import RetryPolicy


def test_exponential_backoff_is_capped():
    policy = RetryPolicy(max_retries=5, base_delay_seconds=0.5, max_delay_seconds=4.0)
    assert [policy.delay_for_retry(n) for n in range(1, 6)] == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_max_attempts_includes_initial_attempt():
    assert RetryPolicy(max_retries=3).max_attempts == 4
