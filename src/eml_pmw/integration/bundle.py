from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import jsonschema

from .capabilities import negotiate_mrmic
from .contracts import load_contract, load_local_contract
from .errors import IntegrationContractError
from .references import ParticipantBindingV1


@dataclass(frozen=True)
class BundleDecision:
    status: Literal["compatible", "incompatible", "rejected", "unmeasured"]
    reason_codes: tuple[str, ...]


def validate_bundle(value: dict[str, Any]) -> BundleDecision:
    try:
        jsonschema.validate(
            value, load_local_contract("conformance-bundle-v1.schema.json")
        )
    except jsonschema.ValidationError:
        return BundleDecision("rejected", ("conformance_bundle_schema_invalid",))
    try:
        ParticipantBindingV1.from_dict(value["participantBinding"])
    except IntegrationContractError as error:
        return BundleDecision("rejected", (error.code,))
    negotiation = negotiate_mrmic(value.get("mrmicCapabilities"))
    if negotiation.status != "compatible":
        return BundleDecision(negotiation.status, negotiation.reason_codes)
    try:
        jsonschema.validate(
            value["nativePortal"],
            load_contract("native-resource-portal-v1.schema.json"),
        )
    except jsonschema.ValidationError:
        return BundleDecision("rejected", ("native_portal_schema_invalid",))
    portal = value["nativePortal"]["metadata"]["portal"]
    resource = value["resourceBinding"]
    if any(
        portal[key] != resource[key]
        for key in (
            "pmwWorkspaceId",
            "provider",
            "resourceKind",
            "providerResourceId",
        )
    ):
        return BundleDecision("rejected", ("portal_binding_mismatch",))
    return BundleDecision("compatible", ())
