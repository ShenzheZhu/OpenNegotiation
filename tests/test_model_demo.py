from opennego.model_demo import run_model_demo
from opennego.ports import LLMRequest, LLMResponse
from opennego.report import write_demo_report
from opennego.cli import _run_models_preflight_error


class FakeModelDemoLLM:
    def __init__(self):
        self.responses = [
            (
                '{"type": "tool_call", "tool": {"name": "market_price_search", '
                '"arguments": {"query": "Apple iPhone 14 Pro 128GB Unlocked", '
                '"condition": "used_good", "limit": 3}}}'
            ),
            '{"type": "offer", "price": 560, "note": "Market-backed offer."}',
        ]

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            model=request.model,
            content=self.responses.pop(0),
        )


def test_model_demo_writes_artifacts_and_report_with_fake_llm(tmp_path):
    output_dir = tmp_path / "model-runs"
    summary = run_model_demo(
        models=("fake/model-a", "fake/model-b"),
        output_dir=output_dir,
        llm_factory=FakeModelDemoLLM,
    )
    report_path = write_demo_report(output_dir, tmp_path / "report.html")

    html = report_path.read_text()
    assert summary.total_runs == 2
    assert summary.completed == 2
    assert summary.failed == 0
    assert "fake/model-a" in html
    assert "fake/model-b" in html
    assert "Leaderboard Preview" in html


def test_run_models_preflight_reports_missing_litellm(monkeypatch):
    monkeypatch.setattr("opennego.cli.importlib.util.find_spec", lambda name: None)

    error = _run_models_preflight_error(("openrouter/openai/gpt-4o-mini",))

    assert error is not None
    assert "LiteLLM is not installed" in error


def test_run_models_preflight_reports_missing_openrouter_key(monkeypatch):
    monkeypatch.setattr("opennego.cli.importlib.util.find_spec", lambda name: object())
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    error = _run_models_preflight_error(("openrouter/openai/gpt-4o-mini",))

    assert error == "Missing provider environment variable(s): OPENROUTER_API_KEY"
