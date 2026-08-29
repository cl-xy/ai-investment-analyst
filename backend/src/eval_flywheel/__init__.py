"""
Outcome-Grounded Evaluation Flywheel.

Turns resolved, outcome-labeled prediction failures into a governed,
reproducible evaluation corpus. Promotion is deterministic (zero LLM calls);
replay and scoring never see the resolved market outcome (no hindsight
leakage). See docs/adr/ for design rationale.

Modules:
- policy: deterministic promotion classification (predictions -> cases)
- capture: full-fidelity payload persistence for promoted cases
- promotion: wiring into the existing prediction-resolution flow
- replay: frozen-input debate-core replay evaluator
- scoring: outcome/quality scoring + guarded comparison decision policy
"""
