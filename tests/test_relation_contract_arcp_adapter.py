from __future__ import annotations

from dataclasses import replace
import unittest

from eml_pmw.relations.arcp_adapter import (
    AuthorityEvaluatorIndeterminate,
    AuthorityEvaluatorPort,
    AuthorityEvaluatorUnavailable,
    DeterministicAuthorityEvaluator,
    OfflineEvaluatorGrant,
    evaluate_with_port,
)
from eml_pmw.relations.errors import RelationContractError
from eml_pmw.relations.canonical import object_content_digest
from eml_pmw.relations.models_authority import (
    AuthorityCandidate,
    AuthorityEvaluationReceipt,
)
from eml_pmw.relations.temporal import NormalizedInstantEvidence
from tests.relation_contract_helpers import (
    assert_relation_error,
    mutate_and_rebind,
    normalized_instant,
    valid_authority_candidate,
)


def candidate() -> AuthorityCandidate:
    return AuthorityCandidate.from_dict(valid_authority_candidate())


def now(value="1500000000", uncertainty_ns=0) -> NormalizedInstantEvidence:
    return NormalizedInstantEvidence.from_dict(
        normalized_instant(value, uncertainty_ns)
    )


def grant_for(item: AuthorityCandidate, **overrides) -> OfflineEvaluatorGrant:
    value = {
        "grant_ref": "evaluator-grant:fixture:1",
        "subject_entity_ref": item.subject_entity_ref,
        "resource_scope": item.requested_resource_scope,
        "action_scope": item.requested_action_scope,
        "max_risk": "R1",
        "named_party_approval_status": "verified",
        "containment_status": "active",
        "allowed_continuity_preconditions": ("none",),
    }
    value.update(overrides)
    return OfflineEvaluatorGrant(**value)


class UnavailableEvaluator:
    def evaluate(self, _candidate, _now):
        raise AuthorityEvaluatorUnavailable("fixture unavailable")


class IndeterminateEvaluator:
    def evaluate(self, _candidate, _now):
        raise AuthorityEvaluatorIndeterminate(
            ("fixture_evidence_unmeasured",)
        )


class RelationContractArcpAdapterTests(unittest.TestCase):
    def setUp(self):
        self.candidate = candidate()
        self.grant = grant_for(self.candidate)
        self.evaluator = DeterministicAuthorityEvaluator(
            self.candidate.evaluator_policy_version,
            (self.grant,),
        )

    def test_fake_returns_separate_deterministic_contract_authorized_receipt(self):
        first = self.evaluator.evaluate(self.candidate, now())
        second = self.evaluator.evaluate(self.candidate, now())
        self.assertEqual(first, second)
        self.assertEqual(first.authority_resolution["status"], "authorized")
        self.assertIn("contract-authorized", first.authority_resolution["sources"])
        self.assertEqual(first.candidate_digest, self.candidate.content_digest)
        self.assertEqual(
            first.authority_resolution["run_id"], self.candidate.run_ref
        )
        self.assertEqual(
            first.authority_resolution["action_id"],
            self.candidate.action_intent_ref,
        )
        self.assertEqual(
            first.authority_resolution["action_hash"],
            self.candidate.action_intent_digest,
        )
        self.assertNotIn("execution", first.authority_resolution)
        self.assertIsInstance(self.evaluator, AuthorityEvaluatorPort)

    def test_unavailable_and_typed_indeterminate_never_become_authorized(self):
        unavailable = evaluate_with_port(
            UnavailableEvaluator(), self.candidate, now()
        )
        self.assertEqual(unavailable.status, "indeterminate")
        self.assertEqual(
            unavailable.reason_codes, ("authority_evaluator_unavailable",)
        )
        typed = evaluate_with_port(
            IndeterminateEvaluator(), self.candidate, now()
        )
        self.assertEqual(typed.status, "indeterminate")
        self.assertEqual(typed.reason_codes, ("fixture_evidence_unmeasured",))

    def test_blocked_or_indeterminate_candidate_is_not_sent_to_evaluator(self):
        for status in ("blocked", "indeterminate"):
            with self.subTest(status=status):
                value = valid_authority_candidate(
                    candidate_status=status,
                    reason_codes=[f"fixture_{status}"],
                )
                blocked = AuthorityCandidate.from_dict(value)
                with assert_relation_error(
                    self, "authority_candidate_not_eligible"
                ):
                    self.evaluator.evaluate(blocked, now())
                with assert_relation_error(
                    self, "authority_candidate_not_eligible"
                ):
                    evaluate_with_port(self.evaluator, blocked, now())

    def test_policy_version_and_receipt_binding_fail_closed(self):
        changed_policy = replace(
            self.candidate, evaluator_policy_version="policy:other:v1"
        )
        with assert_relation_error(self, "evaluator_policy_version_mismatch"):
            self.evaluator.evaluate(changed_policy, now())

        other = AuthorityCandidate.from_dict(
            mutate_and_rebind(
                valid_authority_candidate(),
                {
                    "candidate_id": "candidate:fixture:other",
                    "action_intent_ref": "action:fixture:other",
                },
            )
        )
        other_evaluator = DeterministicAuthorityEvaluator(
            other.evaluator_policy_version, (grant_for(other),)
        )
        wrong_receipt = other_evaluator.evaluate(other, now())

        class WrongReceiptEvaluator:
            def evaluate(self, _candidate, _now):
                return wrong_receipt

        with assert_relation_error(self, "authority_evaluation_binding_mismatch"):
            evaluate_with_port(WrongReceiptEvaluator(), self.candidate, now())

    def test_replayed_receipt_must_match_complete_invocation_time(self):
        original_now = now()
        old_receipt = self.evaluator.evaluate(self.candidate, original_now)

        class ReplayEvaluator:
            def evaluate(self, _candidate, _now):
                return old_receipt

        control = evaluate_with_port(
            ReplayEvaluator(), self.candidate, original_now
        )
        self.assertEqual(control.status, "authorized")

        cases = (
            ("different-time", now("1600000000")),
            ("after-expiry", now("4000000000")),
            ("different-uncertainty", now("1500000000", uncertainty_ns=1)),
            (
                "different-source",
                NormalizedInstantEvidence.from_dict(
                    normalized_instant(
                        "1500000000",
                        0,
                        source_evidence_refs=["evidence:clock:other"],
                    )
                ),
            ),
            (
                "different-instant-ref",
                NormalizedInstantEvidence.from_dict(
                    normalized_instant(
                        "1500000000",
                        0,
                        instant_ref="instant:fixture:other",
                    )
                ),
            ),
            (
                "different-clock-profile",
                NormalizedInstantEvidence.from_dict(
                    normalized_instant(
                        "1500000000",
                        0,
                        clock_profile_id="clock:other:v1",
                    )
                ),
            ),
        )
        for label, invocation_now in cases:
            with self.subTest(label=label):
                with assert_relation_error(
                    self, "authority_evaluation_time_mismatch"
                ):
                    evaluate_with_port(
                        ReplayEvaluator(), self.candidate, invocation_now
                    )

        after_expiry = now("4000000000")
        forged_value = old_receipt.to_dict()
        forged_value["evaluated_at"] = after_expiry.to_dict()
        forged_value["receipt_digest"] = object_content_digest(
            forged_value, "receipt_digest"
        )
        forged_after_expiry = AuthorityEvaluationReceipt.from_dict(forged_value)

        class FreshTimestampExpiredAuthorization:
            def evaluate(self, _candidate, _now):
                return forged_after_expiry

        with assert_relation_error(self, "authority_resolution_stale"):
            evaluate_with_port(
                FreshTimestampExpiredAuthorization(),
                self.candidate,
                after_expiry,
            )

    def test_port_validates_candidate_and_now_before_external_call(self):
        class CallTrap:
            called = False

            def evaluate(self, _candidate, _now):
                self.called = True
                raise AssertionError("external evaluator must not be called")

        trap = CallTrap()
        with assert_relation_error(self, "authority_candidate_invalid"):
            evaluate_with_port(trap, object(), now())
        self.assertFalse(trap.called)

        with assert_relation_error(self, "temporal_evidence_invalid"):
            evaluate_with_port(trap, self.candidate, object())
        self.assertFalse(trap.called)

    def test_each_fake_policy_conjunct_is_the_sole_deciding_factor(self):
        cases = (
            (
                "resource-scope",
                grant_for(self.candidate, resource_scope=("resource:other",)),
                self.candidate,
                now(),
                "denied",
                "fake-policy:scope-not-covered",
            ),
            (
                "action-scope",
                grant_for(self.candidate, action_scope=("action.other",)),
                self.candidate,
                now(),
                "denied",
                "fake-policy:scope-not-covered",
            ),
            (
                "risk",
                grant_for(self.candidate, max_risk="R0"),
                self.candidate,
                now(),
                "denied",
                "fake-policy:risk-exceeded",
            ),
            (
                "approval",
                grant_for(
                    self.candidate, named_party_approval_status="missing"
                ),
                self.candidate,
                now(),
                "multi-party-required",
                "fake-policy:named-party-approval-missing",
            ),
            (
                "containment-blocked",
                grant_for(self.candidate, containment_status="blocked"),
                self.candidate,
                now(),
                "denied",
                "fake-policy:containment-blocked",
            ),
            (
                "containment-unmeasured",
                grant_for(self.candidate, containment_status="unmeasured"),
                self.candidate,
                now(),
                "approval-required",
                "fake-policy:containment-unmeasured",
            ),
            (
                "expiry",
                self.grant,
                self.candidate,
                now("2500000000"),
                "denied",
                "fake-policy:candidate-expired",
            ),
            (
                "continuity",
                self.grant,
                replace(self.candidate, continuity_precondition="checkpoint"),
                now(),
                "denied",
                "fake-policy:continuity-precondition-unsupported",
            ),
        )
        for label, grant, item, instant, status, source in cases:
            with self.subTest(label=label):
                evaluator = DeterministicAuthorityEvaluator(
                    item.evaluator_policy_version, (grant,)
                )
                receipt = evaluator.evaluate(item, instant)
                self.assertEqual(receipt.authority_resolution["status"], status)
                self.assertIn(source, receipt.authority_resolution["sources"])

    def test_missing_ambiguous_grant_and_expiry_overlap_do_not_authorize(self):
        missing = DeterministicAuthorityEvaluator(
            self.candidate.evaluator_policy_version, ()
        ).evaluate(self.candidate, now())
        self.assertEqual(
            missing.authority_resolution["status"], "approval-required"
        )
        self.assertIn(
            "fake-policy:grant-missing", missing.authority_resolution["sources"]
        )

        ambiguous = DeterministicAuthorityEvaluator(
            self.candidate.evaluator_policy_version,
            (
                self.grant,
                grant_for(self.candidate, grant_ref="evaluator-grant:fixture:2"),
            ),
        )
        decision = evaluate_with_port(ambiguous, self.candidate, now())
        self.assertEqual(decision.status, "indeterminate")
        self.assertEqual(decision.reason_codes, ("evaluator_grant_ambiguous",))

        overlap = evaluate_with_port(
            self.evaluator,
            self.candidate,
            now("2000000000", uncertainty_ns=1),
        )
        self.assertEqual(overlap.status, "indeterminate")
        self.assertEqual(overlap.reason_codes, ("candidate_expiry_indeterminate",))

        unmeasured_now = NormalizedInstantEvidence.from_dict(
            normalized_instant(
                "1500000000",
                0,
                verification_status="unmeasured",
                source_evidence_refs=[],
            )
        )
        unmeasured = evaluate_with_port(
            self.evaluator, self.candidate, unmeasured_now
        )
        self.assertEqual(unmeasured.status, "indeterminate")
        self.assertEqual(
            unmeasured.reason_codes, ("temporal_evidence_insufficient",)
        )

    def test_nonavailability_relation_error_is_preserved_not_reclassified(self):
        class TypedFailure:
            def evaluate(self, _candidate, _now):
                raise RelationContractError(
                    "evaluator_policy_invalid", "fixture"
                )

        with assert_relation_error(self, "evaluator_policy_invalid"):
            evaluate_with_port(TypedFailure(), self.candidate, now())


if __name__ == "__main__":
    unittest.main()
