# Autonomous Relation and Contract Profile v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Neo.K selected Inline FCAO; do not dispatch a fresh Superpowers reviewer per task. At most one Twin performs an independent check at a slice boundary or the final candidate.

**Goal:** Build a provider-neutral Fabric relation/contract lifecycle that produces bounded ARCP authority candidates without turning relation, delivery, identity binding, commitment, or contract activation into execution authority.

**Architecture:** EveMissLab PMW Fabric owns portable schemas, immutable lifecycle events, the synthetic append-only reference store, deterministic projection, CLI, and federation wrapping. SEDB-RAL remains a read-only digest-pinned party/binding evidence adapter; ARCP-MVP remains the authority/risk/budget/containment evaluator behind a request/receipt port. The first implementation is offline, synthetic-only, P0/P1, R0/R1, time-bounded, revocable, non-redelegable, and HDUS-portable.

**Tech Stack:** Python 3.11+, stdlib `unittest`, `dataclasses`, `pathlib`, `hashlib`, `importlib.resources`, `jsonschema` Draft 2020-12, existing `eml_wake.canonical` and create-new filesystem helpers, existing PMW federation contracts/store.

**Spec:** `docs/architecture/Autonomous_Relation_and_Contract_Profile_v1.md` at commit `68eedc680bea5c9fabe6ab01e1186c7ca9e1ce15`, SHA-256 `E4249196F43D6169C938387096C11B2EA8613187585F57C2064535C27A9897E1`. The post-approval clarifications add only mechanically required fields already implied by the approved rules: digest-self-exclusion, ActivationPolicy/party-pin completeness, evidence roots, exact `run_ref + action_intent_ref + action_intent_digest` binding, versioned commitments, and transition-authority digest pinning.

## Global Constraints

- Start execution in a new isolated worktree/branch from the reviewed spec commit; do not implement on `main` or on the docs worktree.
- Preserve `Relation != Acceptance != Contract != Representation != AuthorityCandidate != AuthorityResolution != Capability != Commitment != Execution` in every API and reason code.
- Portable schemas and payloads contain only profile-qualified opaque references/URIs; reject drive letters, UNC paths, absolute POSIX paths, `file://`, Python class paths, and SEDB-RAL internal layout.
- Version-one portable payloads are P0/P1 only. P2/P3/private Residence content fails before persistence.
- Autonomous activation is R0/R1 only, finite, policy-bounded, revocable, non-redelegable, `residence_impact=none`, `continuity_impact=none`, and `economic_terms_ref=null`.
- SEDB-RAL is read-only. Only `verified + active + non-ambiguous + exact current ledger_head/view_digest` is sufficient for consensual/authority-bearing paths.
- An admission receipt is provenance only; it never replaces a current RAL view readback.
- Fabric validates profile eligibility but never substitutes for ARCP authority/risk/budget/containment evaluation.
- Every AuthorityCandidate binds one exact `run_ref + action_intent_ref + action_intent_digest`; equal scopes do not make different actions interchangeable.
- `contract.activated` authorizes only the lifecycle transition. It does not authorize candidate requested action/resource scope.
- Grant authority is external, pre-existing, non-descendant, and acyclic; target contract/relation/grant/candidate/receipt descendants cannot bootstrap the grant.
- Federation delivery/materialization/adoption never creates acceptance or activation.
- CTCL is optional for offline tests. Missing/overlapping temporal evidence is `indeterminate`, never a forged instant or false authorization.
- No production registry/private Residence/real resident/real contract/provider/network/Herdr/Claude/Wake/live federation/cloud/HDUS mutation in ordinary implementation or tests.
- Every negative family has a positive control. Every gate includes an executed injected failure that is observed to turn red.
- Use stdlib `unittest`; do not add pytest as a dependency.
- In every command below, `python` means the implementation worktree's clean `.venv\Scripts\python.exe` on Windows (or the active clean virtual environment on CI/other hosts), never an unrelated global interpreter.
- Full verification command: `python -m unittest discover -s tests`.
- Compile command: `python -m compileall -q src`.
- Target package version after the complete profile is `0.4.0`; do not bump it before the final acceptance task.

## File Structure

Create the profile as a focused package rather than extending the generic federation reducer:

```text
src/eml_pmw/relations/
  __init__.py                 exported profile API
  errors.py                   typed reason-code exception
  canonical.py                profile digest domain/version
  references.py               portable-reference validation
  temporal.py                 normalized instant/uncertainty comparison
  policy.py                   activation-policy model and bounded rules
  models_common.py            exact-field helpers and party evidence pins
  models_relation.py          relation and typed exit/termination records
  models_authority.py         grant, representation, acceptance, candidate, receipt
  events.py                   immutable lifecycle event model and kinds
  reducer.py                  pure lifecycle projection/reducer
  activation.py               eligibility, candidate creation, stale-receipt checks
  store.py                    create-new append-only synthetic store
  projector.py                deterministic JSON projection and explain output
  ral_adapter.py              read-only current public-view evidence adapter
  arcp_adapter.py             evaluator protocol and deterministic fake
  federation_adapter.py       P0/P1 wrapping; no automatic acceptance/adoption
  portability.py              portable dependency/resource scanner
  cli.py                      validate/append/project/explain/verify commands

src/eml_pmw/contracts/relation_contract/
  __init__.py
  normalized-instant-evidence-v1.schema.json
  activation-policy-v1.schema.json
  party-evidence-pin-v1.schema.json
  relation-version-v1.schema.json
  exit-path-v1.schema.json
  survival-clause-v1.schema.json
  termination-terms-v1.schema.json
  contract-version-v1.schema.json
  grant-authority-evidence-v1.schema.json
  representation-grant-v1.schema.json
  party-acceptance-v1.schema.json
  commitment-v1.schema.json
  authority-candidate-v1.schema.json
  authority-evaluation-receipt-v1.schema.json
  relation-contract-event-v1.schema.json
  relation-contract-projection-v1.schema.json

tests/
  relation_contract_helpers.py
  test_relation_contract_core.py
  test_relation_contract_domain.py
  test_relation_contract_authority.py
  test_relation_contract_lifecycle.py
  test_relation_contract_activation.py
  test_relation_contract_store.py
  test_relation_contract_projection.py
  test_relation_contract_cli.py
  test_relation_contract_ral_adapter.py
  test_relation_contract_arcp_adapter.py
  test_relation_contract_federation.py
  test_relation_contract_portability.py
  test_relation_contract_packaging.py
  test_relation_contract_offline_e2e.py
```

Do not add SQLite in this profile version. JSON event/object bytes are canonical; JSON projection is the executable oracle. A later derived SQLite index can consume the same projection without becoming canonical.

## Execution Preflight

- [ ] Use `superpowers:using-git-worktrees` to create a new implementation worktree/branch from exact spec/plan head after the plan is approved.
- [ ] Create and activate a clean local environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
```

- [ ] Run the unchanged baseline before writing a RED test:

```powershell
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python -m compileall -q src
git status --short --branch
```

The reviewed docs-worktree baseline is `277 passed / 2 existing skips / 0 failed`. If the implementation worktree differs, stop and identify whether the base commit, interpreter, dependency set, or workspace state differs; do not reinterpret a dirty or failing baseline as a feature RED.

---

## Slice A — Portable Contracts and Pure State Machine

### Task 1: Contract Package, Canonical Digest, Portable References, and Time Policy

**Files:**
- Create: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/errors.py`
- Create: `src/eml_pmw/relations/canonical.py`
- Create: `src/eml_pmw/relations/references.py`
- Create: `src/eml_pmw/relations/temporal.py`
- Create: `src/eml_pmw/relations/policy.py`
- Create: `src/eml_pmw/relations/contracts.py`
- Create: `src/eml_pmw/contracts/relation_contract/__init__.py`
- Create: `src/eml_pmw/contracts/relation_contract/normalized-instant-evidence-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/activation-policy-v1.schema.json`
- Create: `tests/relation_contract_helpers.py`
- Create: `tests/test_relation_contract_core.py`
- Modify: `pyproject.toml` package-data list only; do not bump version yet.

**Interfaces:**
- Produces: `RelationContractError(code: str, message: str)`.
- Produces: `PROFILE_CANON`, `profile_digest(value: dict) -> str`, `object_content_digest(value: dict, digest_field: str = 'content_digest') -> str`.
- Produces: `validate_portable_ref(value: str, field: str) -> str`.
- Produces: `NormalizedInstantEvidence.from_dict(value)`, `compare_instants(left, right) -> Literal['before','after','equal','overlap']`.
- Produces: `ActivationPolicy.from_dict(value)` with `max_activation_duration_ms`, `max_exit_notice_ms`, `max_clock_uncertainty_ns`, allowed risk/evaluator/clock profiles.
- Produces: `load_relation_contract(name: str) -> dict[str, Any]`.
- Test helper produces: `rebind_content_digest(value, digest_field='content_digest')` and `mutate_and_rebind(value, updates, digest_field='content_digest')` for semantic mutations; stale-digest tests intentionally do not call them.

- [ ] **Step 1: Write the failing core tests**

```python
class RelationContractCoreTests(unittest.TestCase):
    def test_profile_digest_is_domain_and_version_bound(self):
        value = {"schema": "fixture/v1", "ref": "entity:fixture:a"}
        first = profile_digest(value)
        self.assertTrue(first.startswith(
            "sha256:arcp-relation-contract-json-nfc-codepoint-v1:"
        ))
        self.assertEqual(first, profile_digest(value))
        self.assertEqual(
            first,
            "sha256:arcp-relation-contract-json-nfc-codepoint-v1:"
            "a8e75e33a4e7bd3f47d5e88e8cf7a0a23af6f6e499b7d18ac7e5bfb8527c8d1b",
        )

    def test_portable_reference_rejects_host_paths(self):
        for value in (
            r"C:\\Users\\fixture\\item.json",
            r"\\\\host\\share\\item.json",
            "/var/lib/fixture/item.json",
            "file:///tmp/item.json",
            "package.module:ClassName",
        ):
            with self.subTest(value=value):
                with assert_relation_error(self, "portable_ref_invalid"):
                    validate_portable_ref(value, "resolver_source_ref")
        self.assertEqual(
            validate_portable_ref("resident:fixture:a", "party_ref"),
            "resident:fixture:a",
        )

    def test_uncertainty_overlap_is_indeterminate(self):
        left = normalized_instant("1000", uncertainty_ns=20)
        right = normalized_instant("1030", uncertainty_ns=20)
        self.assertEqual(compare_instants(left, right), "overlap")

    def test_activation_policy_rejects_r2_and_unbounded_values(self):
        invalid_risk = mutate_and_rebind(valid_activation_policy(), {"max_risk": "R2"})
        with assert_relation_error(self, "activation_policy_invalid"):
            ActivationPolicy.from_dict(invalid_risk)
        with assert_relation_error(self, "activation_policy_invalid"):
            ActivationPolicy.from_dict(mutate_and_rebind(
                valid_activation_policy(), {"max_activation_duration_ms": 0}
            ))

    def test_stale_content_digest_is_distinct_from_semantic_rejection(self):
        stale = valid_activation_policy()
        stale["max_risk"] = "R1" if stale["max_risk"] == "R0" else "R0"
        with assert_relation_error(self, "content_digest_mismatch"):
            ActivationPolicy.from_dict(stale)
```

- [ ] **Step 2: Run the focused tests and capture RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_core.py" -v`

Expected: import failures for `eml_pmw.relations` and missing packaged contracts. Save the command, failing test names, and error summary in the task checkpoint; do not manufacture a RED commit.

- [ ] **Step 3: Implement the canonical and reference primitives**

```python
PROFILE_CANON = "arcp-relation-contract-json-nfc-codepoint-v1"
PROFILE_DOMAIN = b"ARCP-RELATION-CONTRACT\x00"

def profile_digest(value: dict[str, Any]) -> str:
    body = PROFILE_DOMAIN + PROFILE_CANON.encode("ascii") + b"\x00" + canonical_bytes(value)
    return f"sha256:{PROFILE_CANON}:" + hashlib.sha256(body).hexdigest()

def object_content_digest(value: dict[str, Any], digest_field: str = "content_digest") -> str:
    return profile_digest({key: item for key, item in value.items() if key != digest_field})

def rebind_content_digest(value, digest_field="content_digest"):
    rebound = deepcopy(value)
    rebound[digest_field] = object_content_digest(rebound, digest_field)
    return rebound

def mutate_and_rebind(value, updates, digest_field="content_digest"):
    mutated = deepcopy(value)
    mutated.update(deepcopy(updates))
    return rebind_content_digest(mutated, digest_field)

def validate_portable_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or ":" not in value:
        raise RelationContractError("portable_ref_invalid", field)
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "/", "file://")):
        raise RelationContractError("portable_ref_invalid", field)
    if re.fullmatch(r"(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*:[A-Za-z_]\w*", value):
        raise RelationContractError("portable_ref_invalid", field)
    return value
```

Every `valid_*` fixture constructor computes its digest last. Keyword overrides
are applied through `mutate_and_rebind`, never a raw post-digest `dict.update`.
Semantic tests use rebound values; only tests named `stale_*_digest` retain an
old digest deliberately.

Use `eml_wake.canonical.canonical_bytes`; do not create a second JSON normalization algorithm.

- [ ] **Step 4: Implement normalized time comparison and exact activation policy**

```python
@dataclass(frozen=True)
class NormalizedInstantEvidence:
    instant_ref: str
    clock_profile_id: str
    normalized_unix_ns: str
    uncertainty_ns: int
    verification_status: str
    source_evidence_refs: tuple[str, ...]

    @property
    def lower_ns(self) -> int:
        return int(self.normalized_unix_ns) - self.uncertainty_ns

    @property
    def upper_ns(self) -> int:
        return int(self.normalized_unix_ns) + self.uncertainty_ns

def compare_instants(left, right):
    if left.upper_ns < right.lower_ns:
        return "before"
    if right.upper_ns < left.lower_ns:
        return "after"
    if left.lower_ns == right.lower_ns and left.upper_ns == right.upper_ns:
        return "equal"
    return "overlap"
```

`ActivationPolicy.from_dict` must reject unknown/missing fields, booleans used as integers, risk above R1, empty evaluator/clock allowlists, non-positive duration/notice bounds, and uncertainty above its hard bound.

- [ ] **Step 5: Add the two schemas and loader**

Both schemas use Draft 2020-12, `additionalProperties: false`, all fields required, `economic_terms_ref` absent from these primitives, and portable-ref patterns that do not pretend regex alone proves authority. Add `contracts/relation_contract/*.json` to `[tool.setuptools.package-data]`.

- [ ] **Step 6: Run GREEN and one injected mutation**

Run: `python -m unittest discover -s tests -p "test_relation_contract_core.py" -v`

Expected: PASS.

Mutation: temporarily change `PROFILE_DOMAIN` to `b"ARCP-RELATION-CONTRACT-v2\x00"`; the pinned digest test must fail. Restore and rerun GREEN.

- [ ] **Step 7: Commit Task 1**

```bash
git add pyproject.toml src/eml_pmw/relations src/eml_pmw/contracts/relation_contract tests/relation_contract_helpers.py tests/test_relation_contract_core.py
git commit -m "feat: define relation contract core primitives"
```

### Task 2: Party, Relation, Contract, Exit, and Termination Models

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/models_common.py`
- Create: `src/eml_pmw/relations/models_relation.py`
- Create: `src/eml_pmw/contracts/relation_contract/party-evidence-pin-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/relation-version-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/exit-path-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/survival-clause-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/termination-terms-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/contract-version-v1.schema.json`
- Create: `tests/test_relation_contract_domain.py`
- Modify: `tests/relation_contract_helpers.py`

**Interfaces:**
- Produces: `PartyEvidencePin`, `ExitPath`, `SurvivalClause`, `TerminationTerms`, `RelationVersion`, `ContractVersion` immutable dataclasses.
- Every model exposes `from_dict`, `to_dict`, `content_digest` validation, and exact-field rejection.
- `PartyEvidencePin` requires `party_status`, `binding_status`, `binding_ambiguity`, and `adapter_verification_status` as specified by the approved RAL sufficiency rule.
- `ContractVersion.from_dict(value, *, policy: ActivationPolicy) -> ContractVersion` receives the pinned policy explicitly.
- `ContractVersion` requires both `activation_policy_ref` and `activation_policy_digest`; either missing or mismatched is `activation_policy_pin_incomplete`.
- `ContractVersion` has the only canonical relation edge: `relation_version_ref + relation_version_digest`.

- [ ] **Step 1: Write schema/model RED tests**

```python
def test_relation_has_no_canonical_reverse_contract_list(self):
    value = mutate_and_rebind(
        valid_relation_version(), {"contract_refs": ["contract:fixture:a"]}
    )
    with assert_relation_error(self, "unknown_field"):
        RelationVersion.from_dict(value)

def test_contract_requires_exact_relation_pair(self):
    value = mutate_and_rebind(
        valid_contract_version(relation_version_ref="relation:fixture:a:v1"),
        {"relation_version_digest": None},
    )
    with assert_relation_error(self, "relation_version_pin_incomplete"):
        ContractVersion.from_dict(value, policy=ActivationPolicy.from_dict(valid_activation_policy()))

def test_contract_requires_exact_activation_policy_digest(self):
    value = mutate_and_rebind(
        valid_contract_version(), {"activation_policy_digest": "sha256:wrong"}
    )
    with assert_relation_error(self, "activation_policy_digest_mismatch"):
        ContractVersion.from_dict(value, policy=ActivationPolicy.from_dict(valid_activation_policy()))

def test_version_one_economic_and_continuity_boundaries(self):
    for field, invalid in (
        ("economic_terms_ref", "contract:economics:1"),
        ("residence_impact", "migration-required"),
        ("continuity_impact", "continuity-destructive"),
        ("revocable", False),
        ("redelegable", True),
    ):
        value = mutate_and_rebind(valid_contract_version(), {field: invalid})
        with self.subTest(field=field):
            with assert_relation_error(self, "contract_v1_boundary_invalid"):
                ContractVersion.from_dict(value, policy=ActivationPolicy.from_dict(valid_activation_policy()))

def test_every_standing_party_has_bounded_unilateral_exit(self):
    value = mutate_and_rebind(valid_contract_version(), {"exit_paths": []})
    with assert_relation_error(self, "activation_exit_missing"):
        ContractVersion.from_dict(value, policy=ActivationPolicy.from_dict(valid_activation_policy()))
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_domain.py" -v`

Expected: missing model imports and schemas.

- [ ] **Step 3: Implement exact-field model construction**

Create one helper in `models_common.py`:

```python
def require_exact(value: dict[str, Any], fields: set[str], subject: str) -> None:
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise RelationContractError("unknown_field", f"{subject}:{unknown[0]}")
    if missing:
        raise RelationContractError("missing_field", f"{subject}:{missing[0]}")
```

Each model validates portable refs, enum values, list uniqueness, canonical digest, and cross-field constraints. `RelationVersion` has no `contract_refs`. `ContractVersion` accepts either both relation pin fields or two nulls.

- [ ] **Step 4: Implement typed exit and terminal rules**

`ExitPath` requires finite non-negative notice/effective bounds and an allowed effect. For each party term marked `standing_entity=true`, `ContractVersion.from_dict(..., policy=...)` requires at least one unilateral notice path naming that party with `notice_duration_ms <= policy.max_exit_notice_ms`.

`SurvivalClause.class_name` is limited to `audit_retention`, `attribution`, `confidentiality`, `non_repudiation`; `future_authority` is exactly false.

`TerminationTerms` is exact:

```python
terminal_event_kinds == ("contract.expired", "contract.terminated")
terminal_precedence is True
candidate_invalidation == "immediate"
preserve_audit_history is True
commitment_disposition in {"terminate", "preserve_named_survival_clauses"}
```

- [ ] **Step 5: Add and meta-validate all domain schemas**

Tests call `jsonschema.Draft202012Validator.check_schema` for every file and validate positive fixture dictionaries. For each schema, mutate one required field away and one unknown field in; both must reject while the positive control remains accepted.

- [ ] **Step 6: Run GREEN and focused mutations**

Run: `python -m unittest discover -s tests -p "test_relation_contract_domain.py" -v`

Mutations:
- add `contract_refs` to a relation;
- set `future_authority=true`;
- remove the only unilateral exit;
- set `economic_terms_ref` to a string.

Each must fail with its named reason; restore and rerun GREEN.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/models_common.py src/eml_pmw/relations/models_relation.py src/eml_pmw/contracts/relation_contract tests/relation_contract_helpers.py tests/test_relation_contract_domain.py
git commit -m "feat: model bounded relations and contracts"
```

### Task 3: Representation, Acceptance, and Acyclic Grant Authority

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/models_authority.py`
- Create: `src/eml_pmw/relations/authority.py`
- Create: `src/eml_pmw/contracts/relation_contract/grant-authority-evidence-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/representation-grant-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/party-acceptance-v1.schema.json`
- Create: `tests/test_relation_contract_authority.py`
- Modify: `tests/relation_contract_helpers.py`

**Interfaces:**
- Produces: `GrantAuthorityEvidence`, `RepresentationGrant`, `PartyAcceptance`.
- Produces: `validate_grant_authority(root_ref, evidence_by_ref, forbidden_refs, forbidden_digests) -> tuple[str, ...]` returning verified ancestor refs or raising a typed error.
- Produces: `ral_pin_sufficient(pin, *, current_ledger_head, current_view_digest) -> bool`.

- [ ] **Step 1: Write RED tests for the authority graph and exact-target acceptance**

```python
def test_grant_authority_rejects_self_cycle_and_descendant(self):
    root = GrantAuthorityEvidence.from_dict(mutate_and_rebind(
        valid_grant_authority_evidence(),
        {
            "grant_authority_evidence_id": "authority-evidence:a",
            "dependency_refs": ["authority-evidence:a"],
        },
    ))
    with assert_relation_error(self, "representation_authority_circular"):
        validate_grant_authority("authority-evidence:a", {"authority-evidence:a": root}, set(), set())

def test_contract_cannot_bootstrap_its_own_representation(self):
    root = GrantAuthorityEvidence.from_dict(mutate_and_rebind(
        valid_grant_authority_evidence(),
        {"authority_source_ref": "contract:fixture:a:v1"},
    ))
    with assert_relation_error(self, "representation_authority_descendant"):
        validate_grant_authority(
            root.grant_authority_evidence_id,
            {root.grant_authority_evidence_id: root},
            {"contract:fixture:a:v1"},
            {valid_contract_version()["content_digest"]},
        )

def test_acceptance_target_kind_is_digest_bound(self):
    accepted = PartyAcceptance.from_dict(valid_party_acceptance(target_kind="relation"))
    self.assertEqual(accepted.target_kind, "relation")
    invalid = mutate_and_rebind(
        valid_party_acceptance(target_kind="contract"),
        {"target_id": "relation:fixture:a"},
    )
    with assert_relation_error(self, "acceptance_target_kind_mismatch"):
        PartyAcceptance.from_dict(invalid)

def test_observed_or_claimed_ral_pin_is_never_sufficient(self):
    for status in ("observed", "claimed", "unmeasured"):
        pin = PartyEvidencePin.from_dict(mutate_and_rebind(
            valid_party_pin(), {"adapter_verification_status": status}
        ))
        self.assertFalse(ral_pin_sufficient(pin, current_ledger_head="ral-head:1", current_view_digest="ral-view-digest:1"))
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_authority.py" -v`

Expected: missing authority models/functions.

- [ ] **Step 3: Implement complete ancestor-DAG validation**

Use color-marked DFS (`unseen`, `visiting`, `done`). Reject:

```python
if ref in visiting:
    raise RelationContractError("representation_authority_circular", ref)
if ref not in evidence_by_ref:
    raise RelationContractError("representation_authority_missing", ref)
if item.authority_source_ref in forbidden_refs or item.content_digest in forbidden_digests:
    raise RelationContractError("representation_authority_descendant", ref)
```

Return ancestors in deterministic sorted order. Validate `valid_from/expires_at` through normalized evidence and require every grant to be `revocable=true`, `redelegable=false`.

- [ ] **Step 4: Implement the exact RAL sufficiency predicate**

```python
def ral_pin_sufficient(pin, *, current_ledger_head, current_view_digest):
    return (
        pin.resolver_profile_id == "sedb-ral-public-view/v0.2"
        and pin.adapter_verification_status == "verified"
        and pin.party_status == "active"
        and pin.binding_status == "active"
        and pin.binding_ambiguity is False
        and pin.state_head_ref == current_ledger_head
        and pin.state_view_digest == current_view_digest
    )
```

Do not accept an admission receipt or familiar display label as a substitute input.

- [ ] **Step 5: Add the three schemas and contract mutations**

`PartyAcceptance` fields are `target_kind`, `target_id`, `target_version`, `target_digest`; it contains no contract-only duplicate fields. `acceptance_evidence_root_refs[]` is required and counted independently from row IDs. Schema tests reject target-kind/ID prefix mismatch, missing representation digest, duplicate evidence roots, `redelegable=true`, and non-null revocation fields on an initial grant.

- [ ] **Step 6: Run GREEN and red-control mutations**

Run: `python -m unittest discover -s tests -p "test_relation_contract_authority.py" -v`

Mutate DFS to skip the `visiting` check; the cycle test must fail. Restore and rerun GREEN.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/models_authority.py src/eml_pmw/relations/authority.py src/eml_pmw/contracts/relation_contract tests/relation_contract_helpers.py tests/test_relation_contract_authority.py
git commit -m "feat: bind representation and party acceptance"
```

### Task 4: Immutable Events and Pure Lifecycle Reducer

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/events.py`
- Create: `src/eml_pmw/relations/reducer.py`
- Create: `src/eml_pmw/contracts/relation_contract/relation-contract-event-v1.schema.json`
- Create: `tests/test_relation_contract_lifecycle.py`
- Modify: `tests/relation_contract_helpers.py`

**Interfaces:**
- Produces: `RelationContractEvent.from_dict`, `.to_dict`, `.event_digest`.
- Produces: `LifecycleProjection` with relations, contracts, acceptances, grants, active heads, terminal contracts, conflicts, and invalidated candidate digests.
- Produces: `reduce_events(events, objects_by_digest) -> LifecycleProjection`.

- [ ] **Step 1: Write RED lifecycle tests**

```python
def test_activation_atomically_supersedes_old_head(self):
    projection = reduce_events(amendment_activation_sequence(), fixture_objects())
    self.assertEqual(projection.active_heads, {"contract:fixture:a": "event:activate:v2"})
    self.assertIn("candidate-digest:v1", projection.invalidated_candidate_digests)

def test_terminal_precedence_rejects_resume_or_amend(self):
    for event in (resume_after_termination(), amend_after_expiry()):
        with self.subTest(kind=event["event_kind"]):
            with assert_relation_error(self, "terminal_transition_forbidden"):
                reduce_events(terminal_sequence() + [event], fixture_objects())

def test_split_active_heads_are_conflict_not_selection(self):
    projection = reduce_events(concurrent_activation_sequence(), fixture_objects())
    self.assertEqual(projection.contract_states["contract:fixture:a"], "conflicted_heads")
    self.assertNotIn("contract:fixture:a", projection.active_heads)

def test_delivery_or_adoption_event_is_not_party_acceptance(self):
    with assert_relation_error(self, "event_kind_not_allowed"):
        reduce_events([federation_adoption_fixture()], fixture_objects())

def test_every_declared_event_kind_has_one_effect_handler(self):
    self.assertEqual(EVENT_KINDS, frozenset(EVENT_RULES))
    self.assertEqual(len(EVENT_KINDS), 30)

def test_transition_authority_ref_cannot_hide_changed_evidence(self):
    event = RelationContractEvent.from_dict(valid_activation_event())
    changed = mutate_and_rebind(
        valid_grant_authority_evidence(), {"permitted_lifecycle_actions": ["contract.suspended"]}
    )
    with assert_relation_error(self, "transition_authority_digest_mismatch"):
        reduce_events([event], fixture_objects(transition_authority=changed))
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_lifecycle.py" -v`

Expected: missing event/reducer APIs.

- [ ] **Step 3: Implement exact event fields and kind allowlist**

Required event core:

```python
EVENT_FIELDS = {
    "schema", "event_id", "event_kind", "subject_ref", "object_ref",
    "object_digest", "causal_parents", "claimed_actor_ref",
    "representation_grant_ref", "lifecycle_transition_authority_ref",
    "lifecycle_transition_authority_digest",
    "supersedes_active_head", "acceptance_set_digest",
    "representation_set_digest", "party_evidence_set_digest",
    "activation_policy_digest", "created_time", "local_recorded_at",
    "correction_of", "withdraws", "not_claimed",
}
```

The four activation-set/policy fields are non-null only for
`contract.activated`; every other event carries explicit nulls. Activation
requires all four digests and exact equality with a fresh recomputation.
Every authority-required rule also requires both transition-authority ref and
digest; the reducer loads the exact evidence object and rejects a digest/content
mismatch before applying the effect.

Every event requires exactly these non-claims, plus any event-kind-specific additions:

```python
REQUIRED_EVENT_NONCLAIMS = (
    "capability_granted",
    "economic_compensation",
    "global_causal_order",
    "provider_execution",
    "resident_identity_continuity",
)
```

`event_digest` uses its own domain `ARCP-RELATION-CONTRACT-EVENT\x00` and version. Unknown kinds reject. No event field claims provider execution.

- [ ] **Step 4: Implement reducer transition tables**

Define `TransitionRule(object_kind, allowed_states, terminal, authority_mode,
required_evidence, effect_handler)` and one `EVENT_RULES` entry for every
declared kind. Use the following exact inventory; do not infer behavior from
string prefixes:

| Event kind | Object kind | Allowed prior state | Terminal | Required authority/evidence | Projection effect |
|---|---|---|---|---|---|
| `relation.recorded` | relation | absent | no | source evidence; descriptive non-claim | create `observed` |
| `relation.proposed` | relation | absent, disputed | no | current representation + party pin | create/set `proposed` |
| `relation.party_accepted` | acceptance | proposed, partially accepted | no | exact-target acceptance + current representation/pin | add evidence root; derive `accepted` only when complete |
| `relation.disputed` | relation | observed, proposed, accepted | no | disputing party evidence | set `disputed`; no authority grant |
| `relation.withdrawn` | relation | observed, proposed, disputed | yes for version | proposer representation + transition authority ref/digest | set `withdrawn`; invalidate dependent candidates |
| `relation.superseded` | relation | observed, accepted, disputed | yes for version | new relation version + transition authority ref/digest | set `superseded`; link replacement |
| `contract.drafted` | contract | absent | no | claimed actor only; no acceptance claim | create `draft` |
| `contract.proposed` | contract | draft, negotiating | no | proposer representation + transition authority ref/digest | set `proposed` |
| `contract.counterproposed` | contract | proposed, negotiating | no | counterparty representation + new exact contract digest | set `negotiating`; prior acceptances do not transfer |
| `contract.party_accepted` | acceptance | proposed, negotiating, partially accepted | no | exact-target acceptance + current representation/pin | add root; derive `accepted` only when complete |
| `contract.party_acceptance_withdrawn` | acceptance | proposed, negotiating, accepted, active | no | same party representation + acceptance ref | remove current acceptance; preactive -> proposed, active -> suspended; invalidate candidates |
| `contract.rejected` | contract | proposed, negotiating, accepted | yes for version | rejecting party representation + evidence | set `rejected`; invalidate candidates |
| `contract.withdrawn` | contract | draft, proposed, negotiating, accepted | yes for version | proposer representation + transition authority ref/digest | set `withdrawn`; invalidate candidates |
| `contract.activated` | contract | accepted | no | four activation digests + exact transition authority ref/digest | atomically install/supersede active head; invalidate old candidates/receipts |
| `contract.amendment_proposed` | contract | active, suspended | no | new version/digest + proposer representation | create pending new version; old active head remains until new activation |
| `contract.suspended` | contract | active | no | transition authority ref/digest | set `suspended`; invalidate current candidates |
| `contract.resumed` | contract | suspended | no | fresh acceptances/grants/pins/policy + transition authority ref/digest | set `active`; derive fresh candidates only |
| `contract.terminated` | contract | active, suspended | yes | usable ExitPath + transition authority ref/digest | set `terminated`; immediately invalidate future candidates; retain audit |
| `contract.expired` | contract | any nonterminal | yes | verified normalized clock boundary | set `expired`; immediately invalidate future candidates; retain audit |
| `contract.corrected` | contract | any non-tombstoned version | yes for corrected version | correction authority ref/digest + replacement object digest | mark old version corrected/inactive; add replacement branch; never rewrite bytes |
| `contract.tombstoned` | contract | any | yes | tombstone authority ref/digest | retire version semantics; retain event/object/audit |
| `representation.granted` | representation grant | absent | no | acyclic GrantAuthorityEvidence + current principal pin | create `active` grant projection |
| `representation.suspended` | representation grant | active | no | grant authority ref/digest or profile emergency rule | set `suspended`; invalidate dependent candidates |
| `representation.revoked` | representation grant | active, suspended | yes | revocation authority ref/digest | set `revoked`; invalidate dependent candidates |
| `representation.expired` | representation grant | active, suspended | yes | verified normalized clock boundary | set `expired`; invalidate dependent candidates |
| `commitment.created` | commitment | absent | no | active contract digest | create version 1; execution remains not observed |
| `commitment.status_changed` | commitment | prior nonterminal commitment version | according to new status | exact parent version + permitted lifecycle authority | add new version; never replace prior version |
| `authority_candidate.created` | authority candidate | active contract head | no | fresh lifecycle/pin/grant/policy/action/clock set | record diagnostic candidate; only eligible may reach evaluator |
| `authority_candidate.invalidated` | authority candidate | recorded/current | yes | causal invalidating lifecycle event | mark historical/stale; no execution effect |
| `authority_evaluation.recorded` | evaluation receipt | eligible candidate | no | exact candidate digest + evaluator identity/policy | record historical receipt; current status derived by fresh recomputation |

Materialize that table as `EVENT_RULES`; `EVENT_KINDS` is the immutable set of
the same 30 keys. The inventory-completeness test is the gate against adding a
schema enum without reducer behavior or vice versa.

State helpers may use explicit maps such as:

```python
PREACTIVE = {"draft", "proposed", "negotiating", "accepted"}
TERMINAL = {"terminated", "expired"}

ALLOWED = {
    "contract.drafted": {None: "draft"},
    "contract.proposed": {"draft": "proposed", "negotiating": "proposed"},
    "contract.counterproposed": {"proposed": "negotiating", "negotiating": "negotiating"},
    "contract.activated": {"accepted": "active"},
    "contract.suspended": {"active": "suspended"},
    "contract.resumed": {"suspended": "active"},
    "contract.terminated": {"active": "terminated", "suspended": "terminated"},
    "contract.expired": {"active": "expired", "suspended": "expired"},
}

RELATION_ALLOWED = {
    "relation.recorded": {None: "observed"},
    "relation.proposed": {None: "proposed", "disputed": "proposed"},
    "relation.disputed": {"observed": "disputed", "proposed": "disputed", "accepted": "disputed"},
    "relation.withdrawn": {"observed": "withdrawn", "proposed": "withdrawn", "disputed": "withdrawn"},
    "relation.superseded": {"observed": "superseded", "accepted": "superseded", "disputed": "superseded"},
}
```

Required-party acceptances of the same exact digest derive `accepted` for a consensual relation or contract. Descriptive relations remain observed and include the authority non-claim. `contract.activated` requires one current predecessor and performs supersede+invalidation in one reducer step. Two incomparable activation events produce `conflicted_heads`; never select by timestamp or lexical order.

- [ ] **Step 5: Enforce causal and terminal integrity**

Reject missing parents, duplicate event ID with different digest, self-parent, parent cycles, object digest mismatch, acceptance of absent object, acceptance kind mismatch, and any transition descending from a terminal event. Exact duplicate event/digest is idempotent in the reducer input.

Build deterministic topological layers from `causal_parents`. Sorting event
digests inside one concurrent layer is only an iteration/output-stability rule;
it never creates a causal edge or selects a winning contract head.

- [ ] **Step 6: Run GREEN and inject the old-head bug**

Run: `python -m unittest discover -s tests -p "test_relation_contract_lifecycle.py" -v`

Mutation: disable removal of `supersedes_active_head`; the atomic-supersede test must fail by observing two active heads. Restore and rerun GREEN.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/events.py src/eml_pmw/relations/reducer.py src/eml_pmw/contracts/relation_contract/relation-contract-event-v1.schema.json tests/relation_contract_helpers.py tests/test_relation_contract_lifecycle.py
git commit -m "feat: reduce immutable contract lifecycles"
```

### Task 5: Activation Eligibility, Commitments, Authority Candidates, and Fresh Receipt Consumption

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/activation.py`
- Create: `src/eml_pmw/contracts/relation_contract/commitment-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/authority-candidate-v1.schema.json`
- Create: `src/eml_pmw/contracts/relation_contract/authority-evaluation-receipt-v1.schema.json`
- Create: `tests/test_relation_contract_activation.py`
- Modify: `src/eml_pmw/relations/models_authority.py`
- Modify: `tests/relation_contract_helpers.py`

**Interfaces:**
- Produces: versioned `CommitmentRecord`, `AuthorityCandidate`, `AuthorityEvaluationReceipt`.
- Produces: `evaluate_activation(inputs: ActivationInputs) -> ActivationDecision`.
- Produces: `build_authority_candidate(inputs, decision) -> AuthorityCandidate` for eligible/blocked/indeterminate diagnostics; only `eligible` candidates may be sent to an evaluator.
- Produces: `recompute_candidate_from_current_state(*, action_intent, lifecycle_projection, current_party_pins, current_grants, clock, evaluator_profile_id, evaluator_policy_version, policy) -> AuthorityCandidate`.
- Produces: `receipt_is_current(receipt, *, action_intent, lifecycle_projection, current_party_pins, current_grants, clock, evaluator_profile_id, evaluator_policy_version, policy) -> ReceiptCurrency`; it never accepts a caller-supplied candidate as proof of freshness.

- [ ] **Step 1: Write RED activation/currency tests**

```python
def test_lifecycle_transition_authority_does_not_cover_candidate_scope(self):
    inputs = valid_activation_inputs(
        transition_authority_scope=["contract.activated"],
        requested_action_scope=["provider.send"],
    )
    decision = evaluate_activation(inputs)
    self.assertEqual(decision.status, "eligible")
    candidate = build_authority_candidate(inputs, decision)
    self.assertEqual(candidate.requested_action_scope, ("provider.send",))
    self.assertNotIn("provider.send", inputs.transition_authority_scope)

def test_stale_receipt_is_historical_only(self):
    receipt = valid_evaluation_receipt(evaluator_policy_version="policy:v1")
    result = receipt_is_current(
        receipt,
        action_intent=self.action_intent,
        lifecycle_projection=projection_after_amendment(active_head="event:activate:v2"),
        current_party_pins=self.current_party_pins,
        current_grants=self.current_grants,
        clock=normalized_instant("2000"),
        evaluator_profile_id="arcp:fake:v1",
        evaluator_policy_version="policy:v2",
        policy=self.activation_policy,
    )
    self.assertFalse(result.current)
    self.assertEqual(result.reason_code, "authority_resolution_stale")

def test_old_candidate_cannot_override_advanced_ral_head(self):
    receipt = valid_evaluation_receipt()
    advanced_pins = tuple(
        mutate_and_rebind(pin.to_dict(), {"state_head_ref": "ral-head:2"})
        for pin in self.current_party_pins
    )
    result = receipt_is_current(
        receipt,
        action_intent=self.action_intent,
        lifecycle_projection=self.current_projection,
        current_party_pins=tuple(PartyEvidencePin.from_dict(pin) for pin in advanced_pins),
        current_grants=self.current_grants,
        clock=normalized_instant("2000"),
        evaluator_profile_id="arcp:fake:v1",
        evaluator_policy_version="policy:v1",
        policy=self.activation_policy,
    )
    self.assertEqual(result.reason_code, "authority_resolution_stale")

def test_expiry_overlap_is_indeterminate(self):
    inputs = valid_activation_inputs(now=normalized_instant("1000", 20), expires=normalized_instant("1010", 20))
    self.assertEqual(evaluate_activation(inputs).status, "indeterminate")

def test_commitment_has_no_execution_claim(self):
    item = CommitmentRecord.from_dict(valid_commitment(version=1, parent_version_digest=None, execution_refs=[]))
    self.assertEqual(item.status, "active")
    self.assertEqual(item.execution_refs, ())
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_activation.py" -v`

Expected: missing activation APIs/schemas.

- [ ] **Step 3: Implement the activation decision matrix**

`evaluate_activation` checks, in order:

1. one non-conflicted accepted lifecycle head;
2. exact current contract digest;
3. finite policy-bounded effective/expiry interval;
4. current exact acceptances for all required parties;
5. current sufficient party pins;
6. current acyclic representation grants covering lifecycle action;
7. R0/R1 risk and policy allowlist;
8. typed usable exits and termination terms;
9. `residence_impact=none`, `continuity_impact=none`, `economic_terms_ref=null`;
10. lifecycle transition authority covers only the activation append.

Return `eligible`, `blocked`, or `indeterminate` with sorted reason codes. Never return `authorized`.

- [ ] **Step 4: Implement candidate and receipt digest binding**

Candidate digest covers run ref, exact action intent ref/digest, contract digest, active lifecycle head, sorted grant digest set, sorted party-evidence digest set, requested resources/scopes, risk, approval mode, continuity precondition, expiry, clock profile, activation-time ref/evidence digest, evaluator profile, and evaluator policy version.

`receipt_is_current` first calls `recompute_candidate_from_current_state` over
the supplied current projection/pins/grants/clock/policy and action intent. It
never trusts a serialized candidate supplied by the caller. It then compares
every field below:

`recompute_candidate_from_current_state` reruns `ral_pin_sufficient`, complete
grant-authority DAG/expiry/scope checks, active-head selection, acceptance-root
counting, action-intent digest verification, and clock uncertainty checks. An
input labelled current by its caller but failing any verifier is rejected or
indeterminate before candidate construction.

```python
CURRENT_FIELDS = (
    "candidate_digest", "run_ref", "action_intent_ref", "action_intent_digest",
    "active_lifecycle_head", "contract_digest",
    "representation_grant_digest_set", "party_evidence_set_digest",
    "expires_at", "clock_profile_id", "activation_time_ref",
    "activation_time_evidence_digest", "evaluator_profile_id", "evaluator_policy_version",
    "requested_resource_scope", "requested_action_scope", "risk",
)
```

An old receipt remains serializable/projectable but cannot authorize future work.

- [ ] **Step 5: Add schemas and mutation controls**

Schema rejects unknown/missing fields, duplicate roots/scopes, R2+, `candidate_status=authorized`, missing evaluator policy, and a receipt whose embedded resolution lacks `contract-authorized` when the candidate depends on a contract.

- [ ] **Step 6: Run Slice A full GREEN**

Run:

```text
python -m unittest discover -s tests -p "test_relation_contract_*.py" -v
```

Expected: PASS.

Mutation: replace one current grant with `mutate_and_rebind(...)` after receipt
creation; `receipt_is_current` must rebuild a different candidate and become
false while the stored receipt remains readable. Restore and rerun GREEN.

- [ ] **Step 7: Commit Task 5 and record Slice A checkpoint**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/activation.py src/eml_pmw/relations/models_authority.py src/eml_pmw/contracts/relation_contract tests/relation_contract_helpers.py tests/test_relation_contract_activation.py
git commit -m "feat: derive bounded authority candidates"
```

Checkpoint records exact head, focused test count, zero production/private/network/provider effects, and one executed RED mutation per Task 1–5. One Twin may review Slice A; no per-task reviewer fan-out.

---

## Slice B — Append-Only Store, Projection, and CLI

### Task 6: Create-New Append-Only Relation/Contract Store

**Files:**
- Create: `src/eml_pmw/relations/store.py`
- Create: `tests/test_relation_contract_store.py`
- Modify: `src/eml_pmw/relations/__init__.py`

**Interfaces:**
- Produces: `RelationContractStore(root: str | Path)`.
- Produces: `put_object(kind, value) -> StoredObjectResult`.
- Produces: `append_event(event) -> AppendEventResult`.
- Produces: `get_object(content_digest)`, `objects_by_digest() -> dict[str, dict]`, `events()`, `head_digest() -> str | None`, `verify(expected_head: str | None = None) -> StoreVerification`, `repair_indexes() -> RepairResult`.

- [ ] **Step 1: Write RED store tests**

```python
def test_same_version_identity_different_digest_is_quarantined_not_replaced(self):
    store = RelationContractStore(self.root)
    first = store.put_object("contract", valid_contract_version())
    changed = mutate_and_rebind(
        valid_contract_version(), {"scope": ["resource:other#read"]}
    )
    with assert_relation_error(self, "object_identity_collision"):
        store.put_object("contract", changed)
    self.assertEqual(store.get_object(first.content_digest)["scope"], ["resource:fixture#read"])

def test_missing_parent_fails_before_event_publication(self):
    store = RelationContractStore(self.root)
    with assert_relation_error(self, "contract_parent_missing"):
        store.append_event(RelationContractEvent.from_dict(valid_event(causal_parents=["event:missing"])))
    self.assertEqual(store.events(), ())

def test_concurrent_same_identity_different_digest_has_one_winner(self):
    results = run_concurrent_puts(
        self.root,
        mutate_and_rebind(valid_contract_version(), {"scope": ["resource:a#read"]}),
        mutate_and_rebind(valid_contract_version(), {"scope": ["resource:b#read"]}),
    )
    self.assertEqual(sorted(item.status for item in results), ["created", "quarantined"])
    self.assertEqual(len(RelationContractStore(self.root).objects_by_digest()), 1)

def test_root_reparse_or_git_path_is_refused(self):
    for root in (self.git_root, self.reparse_root):
        with self.subTest(root=root):
            with assert_relation_error(self, "storage_root_refused"):
                RelationContractStore(root)

def test_crash_after_bundle_before_index_is_repairable_without_republishing_object(self):
    store = RelationContractStore(self.root, fault_injector=fail_after_object_bundle())
    with assert_relation_error(self, "index_publication_interrupted"):
        store.put_object("contract", valid_contract_version())
    verification = RelationContractStore(self.root).verify()
    self.assertEqual(verification.status, "repairable_index_gap")
    RelationContractStore(self.root).repair_indexes()
    self.assertEqual(RelationContractStore(self.root).verify().status, "internally_consistent")
    self.assertEqual(len(RelationContractStore(self.root).objects_by_digest()), 1)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_store.py" -v`

Expected: missing store APIs.

- [ ] **Step 3: Implement exact disposable layout**

```text
root/
  objects/<kind>/<sha256(canonical identity tuple)>.json
  events/<sha256(event_id)>.json
  indexes/object-digests/<sha256(content_digest)>.json
  indexes/event-digests/<sha256(event_digest)>.json
  duplicates/<sha256(event_id)>/<sha256(delivery_digest)>.json
  quarantine/<reason>/<sha256(input_digest)>.json
```

The object path is the one-winner location. Its single canonical JSON bundle contains:

```text
schema = arcp-relation-contract-object-bundle/0.1
kind
identity_tuple[]
content_digest
canonical_object
bundle_digest
```

The event path is likewise one atomic bundle containing `event_id`,
`event_digest`, canonical event bytes/object, and `bundle_digest`. There is no
separate canonical object/event write before the identity/event-ID winner is
decided.

Use existing `publish_no_replace`/`publish_bytes_no_replace` to atomically
publish each complete winner bundle. Verify no reparse point from root to
target. Reject production-root markers, `.git`, existing unexpected top-level
entries, and non-canonical stored bytes.

Thread locks may reduce local contention but are not the correctness mechanism.
Two processes racing on one identity or event ID target the same one-winner
bundle path: one complete bundle wins; the loser compares against the winner
and writes only quarantine/duplicate evidence. Loser bytes never appear under
`objects/` or `events/` as a second canonical record.

Object identity tuples are exact:

```python
VERSIONED_IDS = {
    "relation": ("relation_id", "version"),
    "contract": ("contract_id", "version"),
    "commitment": ("commitment_id", "version"),
    "activation_policy": ("policy_id", "policy_version"),
    "party_evidence": ("party_ref", "state_head_ref", "state_view_digest"),
}
SINGLE_IDS = {
    "grant_authority": "grant_authority_evidence_id",
    "representation_grant": "representation_grant_id",
    "acceptance": "acceptance_id",
    "authority_candidate": "candidate_id",
    "authority_evaluation": "receipt_digest",
}
DIGEST_FIELDS = {
    "authority_evaluation": "receipt_digest",
}
# Every other persisted object kind uses "content_digest".
```

- [ ] **Step 4: Implement idempotency and collision rules**

- Same object digest and bytes: return `existing`.
- Same logical identity tuple (`kind + object_id + version` for versioned objects) with another digest: quarantine and raise `object_identity_collision`. A later relation/contract version is a different tuple and is allowed.
- Same event ID/digest: record duplicate evidence, no second transition.
- Same event ID/different digest: quarantine and raise `event_id_collision`.
- Missing parent or object digest: reject before publishing the event.
- Digest indexes are derived after the winner bundle. Bundle present/index missing is `repairable_index_gap`; `repair_indexes()` create-new rebuilds indexes from verified bundles. Index present/bundle missing, malformed bundles, or contradictory indexes are invalid/tamper evidence.
- Store verification returns `empty`, `repairable_index_gap`, `internally_consistent`, `checkpoint_verified`, or `invalid`; only exact `expected_head == head_digest()` may produce `checkpoint_verified`/`valid=true`.

`head_digest()` is domain-separated over the sorted set of causal-head event
digests. Each event binds its parents and object digest, so the resulting value
commits transitively to the reachable graph without inventing a total order
between concurrent heads.

- [ ] **Step 5: Run GREEN and destructive-copy controls**

Run: `python -m unittest discover -s tests -p "test_relation_contract_store.py" -v`

In a disposable copy, mutate an object byte, remove one parent event, replace an index, and add an unexpected top-level file. Each verification must return invalid with a distinct code; the untouched control remains internally consistent.

- [ ] **Step 6: Commit Task 6**

```bash
git add src/eml_pmw/relations/store.py src/eml_pmw/relations/__init__.py tests/test_relation_contract_store.py
git commit -m "feat: persist relation contract events append-only"
```

### Task 7: Deterministic Projection and Explain Output

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/projector.py`
- Create: `src/eml_pmw/contracts/relation_contract/relation-contract-projection-v1.schema.json`
- Create: `tests/test_relation_contract_projection.py`

**Interfaces:**
- Produces: `rebuild_projection(store) -> bytes`.
- Produces: `projection_digest(projection_value: dict[str, Any]) -> str`, computed with `projection_digest` omitted before insertion.
- Produces: `explain_subject(store, subject_ref) -> dict[str, Any]`.

- [ ] **Step 1: Write RED projection tests**

```python
def test_rebuild_is_byte_identical_and_input_order_independent(self):
    first = rebuild_projection(store_from_events(self.events))
    second = rebuild_projection(store_from_events(reversed(self.events)))
    self.assertEqual(first, second)

def test_relation_reverse_contract_index_is_derived_only(self):
    value = loads_strict(rebuild_projection(self.store))
    relation = value["relations"]["relation:fixture:a"]
    self.assertEqual(relation["derived_contract_refs"], ["contract:fixture:a"])
    self.assertNotIn("contract_refs", self.store.get_object(self.relation_digest))

def test_explain_separates_acceptance_representation_candidate_resolution_execution(self):
    value = explain_subject(self.store, "contract:fixture:a")
    self.assertEqual(value["execution_status"], "not_observed")
    self.assertIn("acceptance_set_digest", value)
    self.assertIn("representation_set_digest", value)
    self.assertIn("authority_candidate_digest", value)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_projection.py" -v`

- [ ] **Step 3: Implement canonical projection**

Projection keys are sorted and include:

```text
schema
projection_digest
source_event_digests[]
relations{}
contracts{}
representation_grants{}
acceptances{}
commitments{}
authority_candidates{}
authority_evaluations{}
conflicts[]
invalidated_candidate_digests[]
not_claimed[]
```

Projection reports `single_head_active`, `single_head_inactive`, `conflicted_heads`, `blocked`, `indeterminate`, `terminated`, or `expired`. It never picks a conflicted head by wall time or lexical order.

- [ ] **Step 4: Implement explain boundaries**

Explain output lists source refs/digests, acceptance evidence roots, representation validity, current party pins, activation reasons, candidate/evaluator versions, receipt currency, and execution status. It must not collapse these layers into one `authorized` boolean.

- [ ] **Step 5: Run GREEN and corruption proof**

Run: `python -m unittest discover -s tests -p "test_relation_contract_projection.py" -v`

Mutation: change one contract digest in an event without changing object bytes; projection must fail `object_digest_mismatch`. Restore and rerun GREEN.

- [ ] **Step 6: Commit Task 7**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/projector.py src/eml_pmw/contracts/relation_contract/relation-contract-projection-v1.schema.json tests/test_relation_contract_projection.py
git commit -m "feat: project relation contract state deterministically"
```

### Task 8: Typed CLI Without Send Capability

**Files:**
- Create: `src/eml_pmw/relations/cli.py`
- Create: `tests/test_relation_contract_cli.py`
- Modify: `src/eml_pmw/cli.py`

**Interfaces:**
- Produces top-level commands:
  - `relation-contract-validate FILE --kind KIND`
  - `relation-contract-append --root ROOT --object FILE --event FILE`
  - `relation-contract-project --root ROOT`
  - `relation-contract-explain --root ROOT SUBJECT_REF`
  - `relation-contract-verify --root ROOT [--expected-head DIGEST]`

- [ ] **Step 1: Write RED CLI matrix**

```python
def test_cli_exit_contract(self):
    cases = (
        (["relation-contract-validate", self.good, "--kind", "contract"], 0, "valid"),
        (["relation-contract-validate", self.schema_bad, "--kind", "contract"], 2, "rejected"),
        (["relation-contract-project", "--root", self.conflicted_root], 3, "conflicted"),
        (["relation-contract-project", "--root", self.indeterminate_root], 4, "indeterminate"),
        (["relation-contract-validate", self.missing, "--kind", "contract"], 1, "error"),
    )
    for argv, code, status in cases:
        with self.subTest(argv=argv):
            result, output = run_cli(argv)
            self.assertEqual(result, code)
            self.assertEqual(loads_strict(output)["status"], status)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_cli.py" -v`

Expected: unknown subcommands.

- [ ] **Step 3: Implement canonical typed output**

Exit codes:

```text
0 success / valid / internally_consistent
1 unreadable or unparsable input
2 contract/schema/policy rejection
3 unresolved conflict
4 indeterminate / unavailable evidence
```

Every stdout response is one canonical compact JSON object with a final LF and no traceback. Error output contains `status` and `reason_codes` only; local filesystem details stay out of portable evidence.

- [ ] **Step 4: Prove the CLI has no send path**

AST scan `src/eml_pmw/relations` for imports/calls to `socket`, `requests`, `urllib.request`, `http.client`, `subprocess`, provider adapters, Bridge, Wake, Herdr, and cloud SDKs. Inject `import socket` in a temporary copy and prove the gate turns red; untouched source remains green.

- [ ] **Step 5: Run Slice B GREEN**

Run:

```text
python -m unittest discover -s tests -p "test_relation_contract_*.py" -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 8 and record Slice B checkpoint**

```bash
git add src/eml_pmw/relations/cli.py src/eml_pmw/cli.py tests/test_relation_contract_cli.py
git commit -m "feat: expose offline relation contract cli"
```

---

## Slice C — Read-Only RAL and ARCP Evaluator Adapters

### Task 9: Digest-Pinned Read-Only RAL Party Evidence Adapter

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/ral_adapter.py`
- Create: `tests/test_relation_contract_ral_adapter.py`
- Modify: `tests/relation_contract_helpers.py`

**Interfaces:**
- Consumes existing `eml_pmw.federation.ral_adapter.RalAdapterManifest` and `verify_ral_schema_pin`.
- Produces: `RalPartyEvidenceAdapter(manifest, schema_bytes)`.
- Produces: `resolve_party(view_bytes: bytes | None, *, resident_id, instance_id, expected_ledger_head, expected_view_digest) -> PartyEvidencePin`.
- Produces no mutation method.

- [ ] **Step 1: Write RED adapter/current-state tests**

```python
def test_verified_current_unique_binding_produces_sufficient_pin(self):
    adapter = RalPartyEvidenceAdapter(self.manifest, self.schema_bytes)
    pin = adapter.resolve_party(
        self.view_bytes,
        resident_id="resident:fixture:a",
        instance_id="instance:fixture:a:1",
        expected_ledger_head=self.ledger_head,
        expected_view_digest=self.view_digest,
    )
    self.assertTrue(ral_pin_sufficient(pin, current_ledger_head=self.ledger_head, current_view_digest=self.view_digest))

def test_head_advance_and_ambiguous_binding_fail_closed(self):
    cases = (
        (view_with_new_head(), "ral_head_stale"),
        (view_with_two_active_instances(), "party_binding_ambiguous"),
    )
    for view, code in cases:
        with self.subTest(code=code):
            with assert_relation_error(self, code):
                self.adapter.resolve_party(canonical_bytes(view), **self.expected)

def test_admission_receipt_does_not_replace_current_readback(self):
    with assert_relation_error(self, "ral_current_view_required"):
        self.adapter.resolve_party(None, **self.expected)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_ral_adapter.py" -v`

- [ ] **Step 3: Implement canonical-byte and exact-current checks**

Parse with `loads_strict`; require bytes equal `canonical_bytes(value)`. Reuse the existing exact schema/source pin. Resolve exactly one active resident, one named active instance, and one non-ambiguous active binding. Recompute the complete view digest and require exact ledger head/view digest equality.

- [ ] **Step 4: Prove read-only behavior**

Pass read-only bytes/objects into the adapter. No path to the RAL repository or registry is accepted by the portable API. A mutation-trap source object whose write methods raise must remain untouched. Grep/AST gate rejects imports of SEDB-RAL mutation/registration/operations modules.

- [ ] **Step 5: Run GREEN and TOCTOU mutation**

Run: `python -m unittest discover -s tests -p "test_relation_contract_ral_adapter.py" -v`

Mutation: advance the fixture `ledger_head` after producing a pin. Activation must reject the old pin; restore and rerun GREEN.

- [ ] **Step 6: Commit Task 9**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/ral_adapter.py tests/test_relation_contract_ral_adapter.py tests/relation_contract_helpers.py
git commit -m "feat: resolve current ral party evidence read-only"
```

### Task 10: ARCP Evaluator Port and Deterministic Offline Fake

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/arcp_adapter.py`
- Create: `tests/test_relation_contract_arcp_adapter.py`

**Interfaces:**
- Produces: `AuthorityEvaluatorPort` protocol.
- Produces: `DeterministicAuthorityEvaluator(policy_version: str, grants: tuple[...])`.
- Produces: `evaluate(candidate, now) -> AuthorityEvaluationReceipt`.
- Produces: `evaluate_with_port(evaluator, candidate, now) -> EvaluationDecision`, converting only transport/unavailability into `indeterminate` and preserving typed evaluator results.
- No live TypeScript process, MCP, HTTP, subprocess, or provider call.

- [ ] **Step 1: Write RED evaluator-boundary tests**

```python
class AuthorityEvaluatorPort(Protocol):
    def evaluate(
        self,
        candidate: AuthorityCandidate,
        now: NormalizedInstantEvidence,
    ) -> AuthorityEvaluationReceipt: ...

def test_fake_returns_separate_contract_authorized_resolution(self):
    receipt = self.evaluator.evaluate(self.candidate, normalized_instant("2000"))
    self.assertEqual(receipt.authority_resolution["status"], "authorized")
    self.assertIn("contract-authorized", receipt.authority_resolution["sources"])
    self.assertEqual(receipt.candidate_digest, self.candidate.content_digest)
    self.assertEqual(receipt.authority_resolution["run_id"], self.candidate.run_ref)
    self.assertEqual(receipt.authority_resolution["action_id"], self.candidate.action_intent_ref)
    self.assertEqual(receipt.authority_resolution["action_hash"], self.candidate.action_intent_digest)

def test_evaluator_unavailable_never_becomes_authorized(self):
    decision = evaluate_with_port(UnavailableEvaluator(), self.candidate, normalized_instant("2000"))
    self.assertEqual(decision.status, "indeterminate")
    self.assertEqual(decision.reason_codes, ("authority_evaluator_unavailable",))

def test_blocked_or_indeterminate_candidate_is_not_sent_to_evaluator(self):
    for status in ("blocked", "indeterminate"):
        with self.subTest(status=status):
            candidate = AuthorityCandidate.from_dict(mutate_and_rebind(
                valid_authority_candidate(), {"candidate_status": status}
            ))
            with assert_relation_error(self, "authority_candidate_not_eligible"):
                self.evaluator.evaluate(candidate, normalized_instant("2000"))
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_arcp_adapter.py" -v`

- [ ] **Step 3: Implement the port and fake using ARCP's existing vocabulary**

The fake result uses:

```python
derived_resolution_id = (
    "arcp:authority:"
    + hashlib.sha256(candidate.content_digest.encode("utf-8")).hexdigest()[:32]
)
authority_resolution = {
    "schema": "arcp/authority-resolution/0.1",
    "resolution_id": derived_resolution_id,
    "run_id": candidate.run_ref,
    "action_id": candidate.action_intent_ref,
    "action_hash": candidate.action_intent_digest,
    "status": "authorized" | "approval-required" | "multi-party-required" | "denied",
    "sources": ["contract-authorized"],
    "subject_entity_ref": candidate.subject_entity_ref,
    "resource_scope": list(candidate.requested_resource_scope),
    "relation_refs": list(candidate.relation_refs),
    "contract_refs": [candidate.contract_ref],
    "revocable": True,
    "expires_at": candidate.expires_at,
    "continuity_precondition": candidate.continuity_precondition,
}
```

The receipt separately binds evaluator implementation/policy versions and evidence-set digest. Never rename a Fabric eligibility result to ARCP `authorized`.

- [ ] **Step 4: Add mixed risk/scope/approval controls**

Every conjunct is the sole deciding factor once: scope coverage, risk ceiling, named-party approval mode, active containment, expiry, and continuity precondition. Missing evidence returns approval-required/denied/indeterminate according to the explicit fake policy; it never silently expands scope.

- [ ] **Step 5: Run Slice C GREEN**

Run:

```text
python -m unittest discover -s tests -p "test_relation_contract_*.py" -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 10 and record Slice C checkpoint**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/arcp_adapter.py tests/test_relation_contract_arcp_adapter.py
git commit -m "feat: add offline arcp authority evaluator port"
```

---

## Slice D — Federation, HDUS Portability, Packaging, and End-to-End Acceptance

### Task 11: P0/P1 Federation Wrapping Without Automatic Acceptance

**Files:**
- Modify: `src/eml_pmw/relations/__init__.py`
- Create: `src/eml_pmw/relations/federation_adapter.py`
- Create: `tests/test_relation_contract_federation.py`
- Modify: `src/eml_pmw/federation/models.py` only if a profile-neutral validation hook is necessary; do not special-case contract state in the generic store.
- Modify: `tests/federation_helpers.py` only for new allowed event fixtures.

**Interfaces:**
- Produces: `wrap_relation_event(event, *, realm_ref, replica_ref, replica_seq, payload_class) -> tuple[FederatedEvent, bytes]`.
- Produces: `inspect_imported_relation_event(federated_event, payload) -> ImportedRelationObservation`.
- Produces: `adopt_relation_event(observation, explicit_adoption_receipt, local_store) -> AdoptionResult` that appends only the lifecycle event, never a party acceptance not already present in its payload.

- [ ] **Step 1: Write RED federation boundary tests**

```python
def test_delivery_materialization_and_adoption_do_not_create_acceptance(self):
    envelope, payload = wrap_relation_event(self.proposal_event, **self.refs)
    remote = FederationStore(self.remote_root, self.remote_config)
    remote.submit(envelope, payload, delivery_id="delivery:fixture:1")
    observation = inspect_imported_relation_event(envelope, payload)
    adopt_relation_event(observation, explicit_adoption_receipt(), self.relation_store)
    projection = reduce_events(self.relation_store.events(), self.relation_store.objects_by_digest())
    self.assertEqual(projection.acceptances, {})
    self.assertNotEqual(projection.contract_states[self.contract_id], "active")

def test_offline_concurrent_amendments_remain_two_heads(self):
    projection = federate_two_concurrent_amendments()
    self.assertEqual(projection.contract_states[self.contract_id], "conflicted_heads")

def test_child_before_parent_records_pending_dependency_and_retries_idempotently(self):
    child = wrapped_child_event(parent_id="event:parent")
    first = adopt_relation_event(
        inspect_imported_relation_event(*child),
        explicit_adoption_receipt("adoption:child"),
        self.relation_store,
    )
    self.assertEqual(first.status, "pending_dependencies")
    self.assertEqual(first.missing_parent_ids, ("event:parent",))
    adopt_relation_event(
        inspect_imported_relation_event(*wrapped_parent_event()),
        explicit_adoption_receipt("adoption:parent"),
        self.relation_store,
    )
    second = adopt_relation_event(
        inspect_imported_relation_event(*child),
        explicit_adoption_receipt("adoption:child"),
        self.relation_store,
    )
    self.assertEqual(second.status, "adopted")
    self.assertEqual(len([e for e in self.relation_store.events() if e.event_id == "event:child"]), 1)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest discover -s tests -p "test_relation_contract_federation.py" -v`

- [ ] **Step 3: Implement wrapper and import inspection**

Use existing `pmw-federated-event/v1`. Payload bytes are exactly the canonical `RelationContractEvent` bytes; `payload_sha256` binds them. P0/P1 only. `claimed_actor_ref` and `claimed_instance_ref` remain claims. Add all relation/contract event kinds to explicit fixture config allowlists; authority-required event kinds include activation, amendment activation, suspension, resumption, termination, representation grant/suspend/revoke, and conflict resolution.

- [ ] **Step 4: Implement explicit adoption without semantic promotion**

Adoption requires existing receiver-adoption evidence plus successful profile validation. It may copy the exact lifecycle event into the local relation store. It cannot synthesize `relation.party_accepted`, `contract.party_accepted`, `contract.activated`, or an authority receipt from delivery/adoption metadata.

Missing causal parent or referenced object records a durable
`pending_dependencies` adoption state with exact missing IDs and leaves the
profile event unapplied. Integrity/schema/digest failure records quarantine.
After dependencies arrive, retrying the same adoption ID is idempotent and may
append the child exactly once; pending state is retained as history rather than
deleted.

- [ ] **Step 5: Run GREEN and auto-accept mutation**

Run: `python -m unittest discover -s tests -p "test_relation_contract_federation.py" -v`

Mutation: add a deliberate auto-accept branch after adoption; the first boundary test must fail. Restore and rerun GREEN.

- [ ] **Step 6: Commit Task 11**

```bash
git add src/eml_pmw/relations/__init__.py src/eml_pmw/relations/federation_adapter.py src/eml_pmw/federation/models.py tests/test_relation_contract_federation.py tests/federation_helpers.py
git commit -m "feat: federate relation contract events safely"
```

### Task 12: HDUS Portability, Clean Packaging, Offline E2E, and Candidate Evidence

**Files:**
- Create: `src/eml_pmw/relations/portability.py`
- Create: `tests/test_relation_contract_portability.py`
- Create: `tests/test_relation_contract_packaging.py`
- Create: `tests/test_relation_contract_offline_e2e.py`
- Create: `evidence/release/2026-08-26-relation-contract-v1-candidate.json`
- Modify: `pyproject.toml` version and package data.
- Modify: `src/eml_pmw/__init__.py` version.
- Modify: `tests/test_federation_packaging.py` project/package version assertion only; retain historical federation evidence version `0.3.0`.
- Modify: `tests/test_integration_packaging.py` project/package version assertion.
- Modify: `README.md` command/profile documentation and explicit boundaries.

**Interfaces:**
- Produces: `scan_portable_profile(root) -> PortabilityReport`.
- Produces: `run_portable_conformance(realm, party_resolver) -> ConformanceResult` using the same fixtures for every host kind.
- Produces package version `0.4.0` and clean wheel resources.
- Produces one deterministic two-AI synthetic contract demonstration with fake Windows and fake HDUS realms.

- [ ] **Step 1: Write RED portability and clean-wheel tests**

```python
def test_portable_profile_has_no_host_or_private_dependencies(self):
    report = scan_portable_profile(ROOT / "src" / "eml_pmw" / "relations")
    self.assertEqual(report.findings, ())

def test_fake_hdus_passes_same_contract_suite_without_ral_installed(self):
    windows = run_portable_conformance(FakeRealm("windows_host"), FakePartyResolver())
    hdus = run_portable_conformance(FakeRealm("hdus_host"), FakePartyResolver())
    self.assertEqual(windows.semantic_digest, hdus.semantic_digest)

def test_wheel_contains_profile_modules_and_all_schemas(self):
    names = build_and_list_wheel(ROOT)
    self.assertIn("eml_pmw/relations/reducer.py", names)
    for schema in RELATION_CONTRACT_SCHEMAS:
        self.assertIn(f"eml_pmw/contracts/relation_contract/{schema}", names)
```

- [ ] **Step 2: Write RED end-to-end scenario**

The scenario uses two synthetic AI entities and no real registry/provider:

```text
create verified fixture party pins
-> issue two external acyclic representation grants
-> record consensual relation proposal and exact acceptances
-> propose R1 contract with finite expiry and unilateral exits
-> accept exact contract digest
-> activate one head
-> derive AuthorityCandidate
-> deterministic ARCP fake returns contract-authorized receipt
-> create commitment with execution_refs=[]
-> amend contract and atomically invalidate old candidate/receipt
-> terminate new head
-> prove future candidate rejected while audit/history remains
-> wrap selected P0 events through fake Windows and fake HDUS federation realms
```

Run: `python -m unittest discover -s tests -p "test_relation_contract_*.py" -v`

Expected: missing portability/package/E2E pieces.

- [ ] **Step 3: Implement static portability scan**

AST findings include imports/calls for Win32, `winreg`, `ctypes.windll`, `socket`, HTTP libraries, `subprocess`, Bridge/Wake/Herdr/provider SDKs, SEDB-RAL mutation modules, and absolute-path literals. Resource scan checks every packaged JSON/Markdown fixture for drive letters, UNC, `/home/`, `/var/`, `file://`, Python class paths, private Residence markers, and P2/P3 payload declarations.

Create a temporary copied module containing `import winreg` and a schema containing `C:\\fixture`; both scans must turn red while the actual profile remains green.

- [ ] **Step 4: Complete E2E and exact boundary assertions**

The E2E asserts:

```python
self.assertEqual(effect_counts, {
    "network_calls": 0,
    "provider_calls": 0,
    "production_registry_writes": 0,
    "private_reads": 0,
    "real_contracts": 0,
})
self.assertEqual(final_projection["contracts"][contract_id]["state"], "terminated")
self.assertEqual(final_projection["contracts"][contract_id]["execution_status"], "not_observed")
self.assertTrue(final_projection["audit_history_retained"])
```

The same semantic projection digest is produced by fake Windows and fake HDUS adapters.

- [ ] **Step 5: Bump version and document actual commands/boundaries**

Set `pyproject.toml` and `eml_pmw.__version__` to `0.4.0`. README lists the five relation-contract CLI commands and retains explicit current-state boundaries: no real contract, no provider action, no live ARCP, no production RAL mutation, no employment/economics.

In `tests/test_federation_packaging.py`, split the assertions explicitly:

```python
def test_historical_federation_evidence_remains_0_3_0(self):
    value = json.loads((ROOT / "evidence/release/2026-08-25-federation-v1-acceptance.json").read_text(encoding="utf-8"))
    self.assertEqual(value["version"], "0.3.0")

def test_current_project_and_package_version_are_0_4_0(self):
    self.assertEqual(project_version(ROOT), "0.4.0")
    self.assertEqual(eml_pmw.__version__, "0.4.0")
```

Do not mechanically replace historical `0.3.0` evidence assertions.

- [ ] **Step 6: Run the complete clean verification**

Run from a clean declared test environment:

```text
python -m pip install -e ".[test]"
python -m unittest discover -s tests
python -m compileall -q src
python -m build --wheel --no-isolation
eml-pmw --help
eml-pmw relation-contract-validate --help
eml-pmw relation-contract-append --help
eml-pmw relation-contract-project --help
eml-pmw relation-contract-explain --help
eml-pmw relation-contract-verify --help
git diff --check
```

Expected: all commands exit 0; only documented platform permission skips remain; wheel contains every profile module/schema; tracked publication tree is valid.

- [ ] **Step 7: Execute the acceptance mutation matrix**

Run at least one deliberate failure plus one positive control for each domain:

```text
canonical digest/version
portable refs
time uncertainty
relation vs authority
exact target acceptance
grant DAG/cycle/descendant
RAL current-head sufficiency
terminal lifecycle precedence
atomic active-head supersede
old receipt replay
typed exit/survival
store mutation/deletion/collision
projection determinism
CLI typed exits
federation adoption-is-not-acceptance
HDUS/RAL-absent portability
no-send/no-provider/no-private scan
```

Keep the raw matrix outputs in an untracked disposable checkpoint at this step.
They record command, injected change, expected red code, observed red result,
restored green result, current tree digest, test counts, wheel SHA-256, and
effect counts. Do not create the tracked release evidence yet. CTCL status is
honest: absence of a CTCL call is `not_performed`, not a fabricated instant.

- [ ] **Step 8: Commit the code candidate H1 without tracked review evidence**

Commit only implementation, schemas, tests, version, and README. The resulting
exact commit is `H1`; record its commit and tree IDs after creation.

```bash
git add src/eml_pmw/relations/portability.py tests/test_relation_contract_portability.py tests/test_relation_contract_packaging.py tests/test_relation_contract_offline_e2e.py tests/test_federation_packaging.py tests/test_integration_packaging.py pyproject.toml src/eml_pmw/__init__.py README.md
git commit -m "feat: complete autonomous relation contract profile"
git rev-parse HEAD
git rev-parse HEAD^{tree}
```

- [ ] **Step 9: Run the one final Twin review against exact H1**

The Twin reviews exact H1 once across: schema seams, event-inventory coverage,
circular authority, lifecycle double truth, stale receipt/current-state replay,
cross-process one-winner storage, RAL read-only boundary, federation
non-promotion/pending dependencies, HDUS portability, clean install, and effect
counts. The implementer independently reproduces any finding. If code changes,
create a replacement code candidate H1' and review that exact replacement; do
not write release evidence for a superseded candidate.

- [ ] **Step 10: Create tracked evidence for reviewed H1, then commit evidence-only H2**

After the Twin accepts the final H1, create
`evidence/release/2026-08-26-relation-contract-v1-candidate.json` containing:

```text
schema = pmw-relation-contract-v1-candidate-evidence/0.1
version = 0.4.0
reviewed_source_head = H1
reviewed_source_tree = H1^{tree}
review_artifact_ref
review_artifact_sha256
full_test_counts
focused_test_counts
wheel_sha256
mutation_matrix[]
effect_counts
ctcl_status
not_claimed[]
```

The tracked evidence does not contain or predict H2. Verify the JSON/schema and
then commit exactly the evidence file:

```bash
git add evidence/release/2026-08-26-relation-contract-v1-candidate.json
git commit -m "docs: record reviewed relation contract candidate"
git diff --name-only HEAD^ HEAD
```

Expected diff: only the evidence file. The resulting commit is H2 and H1 must
be its ancestor with the reviewed tree unchanged below the evidence-only commit.

- [ ] **Step 11: Write the external final-head handoff, routine push, and stop before PR/merge**

Write a durable task handoff outside the tracked evidence file containing
`reviewed_source_head=H1`, `final_feature_head=H2`, both tree IDs, evidence-file
digest, review digest, and `git merge-base --is-ancestor H1 H2` result. This
external handoff may name H2 because it is written after H2 exists; it is not a
self-referential tracked artifact.

Push the scoped feature branch after local verification and report exact local/upstream/remote SHA equality. Do not open/merge a PR, release, deploy, update production capability cards, create real relations/contracts, or call providers without a new action-time instruction from Neo.K.

---

## Plan Self-Review Checklist

- [ ] Every normative spec section maps to at least one task.
- [ ] Relation/contract/representation/authority/commitment/execution remain distinct in models, CLI, projection, and explain output.
- [ ] The grant-authority graph cannot use target/descendant artifacts as its root.
- [ ] RelationVersion has no canonical reverse contract list.
- [ ] PartyAcceptance supports relation and contract exact targets.
- [ ] Amendment activation is atomic and terminal precedence cannot be crossed.
- [ ] RAL sufficiency is exact verified/current-state only.
- [ ] Receipt currency requires fresh candidate/head/policy/clock/evidence equality.
- [ ] Exit, survival, termination, and normalized time are typed and tested.
- [ ] Federation adoption never synthesizes acceptance or activation.
- [ ] Fake HDUS passes without RAL installed and portable code contains no host internals.
- [ ] No code task requires a live provider, network, real resident, private Residence, or production registry.
- [ ] Each task has a focused RED, focused GREEN, mutation/red-control, and commit.
- [ ] Final package/wheel/CLI/full-suite/publication verification is explicit.
- [ ] No step authorizes merge, release, deployment, or a real contract.
