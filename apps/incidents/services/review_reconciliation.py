"""
Review Reconciliation Engine for Human HSE Adjudication.
Calculates deterministic alignment across:
- Statistical Machine Learning Model Assessment
- Rule-Grounded Safety Engineering Assessment
- Human HSE Reviewer Adjudication
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


class ReviewAgreementState:
    AGREEMENT = "AGREEMENT"
    MODEL_RULE_HUMAN_TRIPLE_AGREEMENT = "MODEL_RULE_HUMAN_TRIPLE_AGREEMENT"
    HUMAN_OVERRIDES_MODEL = "HUMAN_OVERRIDES_MODEL"
    HUMAN_OVERRIDES_RULE = "HUMAN_OVERRIDES_RULE"
    HUMAN_INSUFFICIENT_INFORMATION = "HUMAN_INSUFFICIENT_INFORMATION"
    THREE_WAY_DISAGREEMENT = "THREE_WAY_DISAGREEMENT"


@dataclass
class ReviewReconciliation:
    human_decision: str
    model_prediction: Optional[str]
    rule_decision: Optional[str]
    model_score: Optional[float]
    agreement_state: str
    model_vs_human: str  # AGREE, DISAGREE, HUMAN_INSUFFICIENT, NOT_APPLICABLE
    rule_vs_human: str   # AGREE, DISAGREE, HUMAN_INSUFFICIENT, NOT_APPLICABLE
    model_vs_rule: str   # AGREE, DISAGREE, NOT_APPLICABLE
    explanation: str
    action_implication: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "human_decision": self.human_decision,
            "model_prediction": self.model_prediction,
            "rule_decision": self.rule_decision,
            "model_score": self.model_score,
            "agreement_state": self.agreement_state,
            "model_vs_human": self.model_vs_human,
            "rule_vs_human": self.rule_vs_human,
            "model_vs_rule": self.model_vs_rule,
            "explanation": self.explanation,
            "action_implication": self.action_implication,
        }


def normalize_decision_label(raw: Any) -> Optional[str]:
    """Normalize boolean or string decisions into canonical PSIF, NOT_PSIF, INSUFFICIENT_INFORMATION."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return "PSIF" if raw else "NOT_PSIF"
    clean = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    if clean in ("PSIF", "IS_PSIF", "TRUE", "1"):
        return "PSIF"
    if clean in ("NOT_PSIF", "NON_PSIF", "FALSE", "0"):
        return "NOT_PSIF"
    if clean in ("INSUFFICIENT_INFORMATION", "INSUFFICIENT", "UNCERTAIN", "UNKNOWN"):
        return "INSUFFICIENT_INFORMATION"
    return clean


def calculate_review_reconciliation(
    human_decision: str,
    model_prediction: Optional[Any],
    rule_decision: Optional[Any],
    model_score: Optional[float] = None,
) -> ReviewReconciliation:
    """
    Calculate tripartite agreement/disagreement across Model, Rule, and Human.
    Does NOT treat disagreement as an error; disagreement is an expected, auditable safety signal.
    """
    norm_human = normalize_decision_label(human_decision) or "INSUFFICIENT_INFORMATION"
    norm_model = normalize_decision_label(model_prediction)
    norm_rule = normalize_decision_label(rule_decision)

    # 1. Human Insufficient Information
    if norm_human == "INSUFFICIENT_INFORMATION":
        m_vs_r = (
            "AGREE"
            if (norm_model and norm_rule and norm_model == norm_rule)
            else "DISAGREE" if (norm_model and norm_rule) else "NOT_APPLICABLE"
        )
        return ReviewReconciliation(
            human_decision=norm_human,
            model_prediction=norm_model,
            rule_decision=norm_rule,
            model_score=model_score,
            agreement_state=ReviewAgreementState.HUMAN_INSUFFICIENT_INFORMATION,
            model_vs_human="HUMAN_INSUFFICIENT",
            rule_vs_human="HUMAN_INSUFFICIENT",
            model_vs_rule=m_vs_r,
            explanation=(
                "Human HSE expert determined that available incident documentation lacks essential factual "
                "context to establish or refute the credible SIF precursor pathway."
            ),
            action_implication="Investigative field verification required to collect missing factual dimensions.",
        )

    # Pairwise relations
    m_vs_h = (
        "AGREE"
        if (norm_model and norm_human == norm_model)
        else "DISAGREE" if norm_model else "NOT_APPLICABLE"
    )
    r_vs_h = (
        "AGREE"
        if (norm_rule and norm_human == norm_rule)
        else "DISAGREE" if norm_rule else "NOT_APPLICABLE"
    )
    m_vs_r = (
        "AGREE"
        if (norm_model and norm_rule and norm_model == norm_rule)
        else "DISAGREE" if (norm_model and norm_rule) else "NOT_APPLICABLE"
    )

    # 2. Both Model and Rule available
    if norm_model and norm_rule:
        if norm_human == norm_model == norm_rule:
            return ReviewReconciliation(
                human_decision=norm_human,
                model_prediction=norm_model,
                rule_decision=norm_rule,
                model_score=model_score,
                agreement_state=ReviewAgreementState.MODEL_RULE_HUMAN_TRIPLE_AGREEMENT,
                model_vs_human=m_vs_h,
                rule_vs_human=r_vs_h,
                model_vs_rule=m_vs_r,
                explanation=(
                    f"Triple consensus achieved: Statistical ML model, rule-grounded safety engineering, "
                    f"and human HSE adjudication unanimously agree on '{norm_human}'."
                ),
                action_implication="High-confidence determination. Suitable for automated reporting and standard closure.",
            )

        if norm_human == norm_rule and norm_human != norm_model:
            return ReviewReconciliation(
                human_decision=norm_human,
                model_prediction=norm_model,
                rule_decision=norm_rule,
                model_score=model_score,
                agreement_state=ReviewAgreementState.HUMAN_OVERRIDES_MODEL,
                model_vs_human=m_vs_h,
                rule_vs_human=r_vs_h,
                model_vs_rule=m_vs_r,
                explanation=(
                    f"Human HSE expert concurred with the rule-grounded safety assessment ({norm_rule}), "
                    f"overriding the statistical ML prediction ({norm_model})."
                ),
                action_implication=(
                    "Human adjudication serves as official ground truth. Logged for future model fine-tuning "
                    "without modifying historical inference."
                ),
            )

        if norm_human == norm_model and norm_human != norm_rule:
            return ReviewReconciliation(
                human_decision=norm_human,
                model_prediction=norm_model,
                rule_decision=norm_rule,
                model_score=model_score,
                agreement_state=ReviewAgreementState.HUMAN_OVERRIDES_RULE,
                model_vs_human=m_vs_h,
                rule_vs_human=r_vs_h,
                model_vs_rule=m_vs_r,
                explanation=(
                    f"Human HSE expert validated the statistical ML prediction ({norm_model}), "
                    f"overriding the deterministic rule assessment ({norm_rule})."
                ),
                action_implication=(
                    "Indicates potential nuance or operational context captured by language representation "
                    "beyond rigid rule heuristics."
                ),
            )

        if norm_human != norm_model and norm_human != norm_rule:
            if norm_model != norm_rule:
                return ReviewReconciliation(
                    human_decision=norm_human,
                    model_prediction=norm_model,
                    rule_decision=norm_rule,
                    model_score=model_score,
                    agreement_state=ReviewAgreementState.THREE_WAY_DISAGREEMENT,
                    model_vs_human=m_vs_h,
                    rule_vs_human=r_vs_h,
                    model_vs_rule=m_vs_r,
                    explanation=(
                        f"Three-way divergence detected: Human reviewer adjudicated '{norm_human}', "
                        f"ML model predicted '{norm_model}', and rule engine evaluated '{norm_rule}'."
                    ),
                    action_implication="High-priority case flagged for secondary committee review and qualitative audit.",
                )
            else:
                return ReviewReconciliation(
                    human_decision=norm_human,
                    model_prediction=norm_model,
                    rule_decision=norm_rule,
                    model_score=model_score,
                    agreement_state=ReviewAgreementState.HUMAN_OVERRIDES_MODEL,
                    model_vs_human=m_vs_h,
                    rule_vs_human=r_vs_h,
                    model_vs_rule=m_vs_r,
                    explanation=(
                        f"Human expert exercised authoritative adjudication ({norm_human}), "
                        f"overriding both automated systems ({norm_model})."
                    ),
                    action_implication="Adjudication recorded as authoritative ground truth.",
                )

    # 3. Single automated system available
    if (norm_model and norm_human == norm_model) or (norm_rule and norm_human == norm_rule):
        state = ReviewAgreementState.AGREEMENT
        expl = f"Human adjudication aligns with available automated safety assessment ({norm_human})."
    elif norm_model:
        state = ReviewAgreementState.HUMAN_OVERRIDES_MODEL
        expl = f"Human adjudication ({norm_human}) overrides statistical model ({norm_model})."
    elif norm_rule:
        state = ReviewAgreementState.HUMAN_OVERRIDES_RULE
        expl = f"Human adjudication ({norm_human}) overrides rule engine ({norm_rule})."
    else:
        state = ReviewAgreementState.AGREEMENT
        expl = f"Independent human adjudication recorded as {norm_human} (no prior automated baseline)."

    return ReviewReconciliation(
        human_decision=norm_human,
        model_prediction=norm_model,
        rule_decision=norm_rule,
        model_score=model_score,
        agreement_state=state,
        model_vs_human=m_vs_h,
        rule_vs_human=r_vs_h,
        model_vs_rule=m_vs_r,
        explanation=expl,
        action_implication="Human adjudication recorded as authoritative ground truth.",
    )
