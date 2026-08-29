"""
Task 7: structural validation of GitHub Actions workflow YAML.

Verifies, without ever executing a workflow:
  - ci.yml (pull_request/push CI) contains no calls to production endpoints
    or LLM-bound secrets — it must remain deterministic and API-free.
  - calibration-resolve.yml (zero-LLM promotion + resolution) is scheduled
    or manually dispatched, never wired to pull_request/push.
  - eval-flywheel-trigger.yml (LLM-bound bounded evaluation) is
    workflow_dispatch ONLY — no `schedule` key, and never wired to
    pull_request/push, since it consumes real LLM budget.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML not installed")

WORKFLOWS_DIR = Path(__file__).parent.parent.parent / ".github" / "workflows"


def _load_workflow(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"Workflow file not found: {path}"
    return yaml.safe_load(path.read_text())


class TestCiWorkflowStaysApiFree:
    def test_ci_yml_has_no_pull_request_calls_to_production_urls(self):
        raw_text = (WORKFLOWS_DIR / "ci.yml").read_text()
        # CI must never reference the scheduler token or production trigger
        # URLs — those are reserved for the dedicated scheduled/manual
        # workflows, never for pull_request/push-triggered jobs.
        assert "SCHEDULER_SECRET_TOKEN" not in raw_text
        assert "EVAL_FLYWHEEL_TRIGGER_URL" not in raw_text
        assert "CALIBRATION_RESOLVE_URL" not in raw_text

    def test_ci_yml_triggers_on_pull_request_and_push_only(self):
        workflow = _load_workflow("ci.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert set(triggers.keys()) <= {"push", "pull_request"}


class TestCalibrationResolveWorkflow:
    def test_is_scheduled_or_manually_dispatchable(self):
        workflow = _load_workflow("calibration-resolve.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert "schedule" in triggers or "workflow_dispatch" in triggers

    def test_never_triggered_by_pull_request_or_push(self):
        workflow = _load_workflow("calibration-resolve.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert "pull_request" not in triggers
        assert "push" not in triggers

    def test_uses_scheduler_token_auth(self):
        raw_text = (WORKFLOWS_DIR / "calibration-resolve.yml").read_text()
        assert "SCHEDULER_SECRET_TOKEN" in raw_text
        assert "x-scheduler-token" in raw_text


class TestEvalFlywheelTriggerWorkflowIsManualOnly:
    def test_has_no_schedule_trigger(self):
        """This workflow makes real LLM calls; it must never run on a fixed
        cadence, only when a human explicitly dispatches it."""
        workflow = _load_workflow("eval-flywheel-trigger.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert "schedule" not in triggers

    def test_has_workflow_dispatch_trigger(self):
        workflow = _load_workflow("eval-flywheel-trigger.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert "workflow_dispatch" in triggers

    def test_never_triggered_by_pull_request_or_push(self):
        workflow = _load_workflow("eval-flywheel-trigger.yml")
        triggers = workflow.get(True, workflow.get("on", {}))
        assert "pull_request" not in triggers
        assert "push" not in triggers

    def test_uses_scheduler_token_auth(self):
        raw_text = (WORKFLOWS_DIR / "eval-flywheel-trigger.yml").read_text()
        assert "SCHEDULER_SECRET_TOKEN" in raw_text
        assert "x-scheduler-token" in raw_text
