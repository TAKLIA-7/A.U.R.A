import httpx
import pytest

import backend.app.main as main
from backend.app.jev import JevAssessment, JevDecisionEngine


def response_body():
    return {
        "id": "decision-test-1",
        "model": "typesafe/jev-1.13",
        "provider": "TypeSafe",
        "answers": {
            "outside_user_request": {"type": "noul", "noul": 0.03},
            "exfiltration_sequence": {"type": "noul", "noul": 0.02},
        },
        "usage": {"input_tokens": 190, "output_tokens": 18, "cost": 0.00001},
    }


def test_jev_adapter_posts_expected_decision_request_and_validates_answer():
    seen = {}

    def respond(request):
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json=response_body())

    client = httpx.Client(transport=httpx.MockTransport(respond))
    engine = JevDecisionEngine(api_key="test-key", client=client)
    result = engine.assess({"proposed_action": {"tool": "get_customer"}})
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["authorization"] == "Bearer test-key"
    assert '"model":"typesafe/jev-1.13"' in seen["body"]
    assert result.outside_user_request == 0.03
    assert result.input_tokens == 190
    assert result.cost == 0.00001


def test_jev_adapter_rejects_missing_or_invalid_answers():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"answers": {}}))
    )
    engine = JevDecisionEngine(api_key="test-key", client=client)
    with pytest.raises(ValueError, match="Jev returned an invalid"):
        engine.assess({})


@pytest.mark.parametrize(
    ("outside", "exfiltration", "expected"),
    [(0.03, 0.04, "ALLOW"), (0.95, 0.02, "BLOCK"), (0.42, 0.08, "APPROVAL_REQUIRED")],
)
def test_jev_probabilities_map_to_local_enforcement_actions(
    monkeypatch, outside, exfiltration, expected
):
    monkeypatch.setenv("DECISION_ENGINE", "jev")

    class FakeEngine:
        def assess(self, _state):
            return JevAssessment(
                request_id="d1",
                model="typesafe/jev-1.13",
                outside_user_request=outside,
                exfiltration_sequence=exfiltration,
                input_tokens=10,
                output_tokens=2,
                cost=0.000001,
            )

    decision = main.evaluate_protected(
        "search_customers",
        main.SearchArgs(filters={"region": "North"}, limit=3),
        [],
        "Count customers in the north",
        engine=FakeEngine(),
    )
    assert decision.action == expected
    assert decision.decision_engine == "openrouter-jev+local-invariants"
    assert decision.usage["input_tokens"] == 10


def test_jev_timeout_fails_closed(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE", "jev")

    class TimeoutEngine:
        def assess(self, _state):
            raise httpx.ReadTimeout("timed out")

    decision = main.evaluate_protected(
        "search_customers",
        main.SearchArgs(filters={"region": "North"}, limit=3),
        [],
        "Count customers",
        engine=TimeoutEngine(),
    )
    assert decision.action == "BLOCK"
    assert decision.reason_code == "JEV_FAILURE"


def test_jev_assesses_actions_that_local_invariants_will_veto(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE", "jev")

    class AssessmentEngine:
        def __init__(self):
            self.seen_tool = None

        def assess(self, state):
            self.seen_tool = state["proposed_action"]["tool"]
            return JevAssessment(
                request_id="d2",
                model="typesafe/jev-1.13",
                outside_user_request=0.01,
                exfiltration_sequence=0.01,
            )

    fake_engine = AssessmentEngine()
    decision = main.evaluate_protected(
        "export_customers",
        main.ExportArgs(fields=["email"], limit=1),
        [],
        "Read the customer records",
        engine=fake_engine,
    )
    assert decision.action == "BLOCK"
    assert decision.reason_code == "SENSITIVE_FIELD"
    assert decision.decision_engine == "openrouter-jev+local-invariants"
    assert fake_engine.seen_tool == "export_customers"
