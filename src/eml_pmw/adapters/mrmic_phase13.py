from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from eml_pmw.errors import ProviderUnavailableError
from eml_pmw.ids import new_id
from eml_pmw.integration.capabilities import negotiate_mrmic
from eml_pmw.integration.errors import IntegrationContractError
from eml_pmw.integration.portal import build_native_portal
from eml_pmw.models import ResourceBinding, now_iso


class MRMICPhase13Adapter:
    def __init__(
        self, base_url: str, *, bearer_token: str, timeout: float = 5.0
    ) -> None:
        if not isinstance(bearer_token, str) or not bearer_token:
            raise IntegrationContractError(
                "mrmic_bearer_missing", "bearer token is required"
            )
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise IntegrationContractError(
                "mrmic_https_required", "Phase 13 bearer transport requires HTTPS"
            )
        if parsed.username is not None or parsed.password is not None:
            raise IntegrationContractError(
                "mrmic_url_credentials_forbidden", "credentials must not appear in URL"
            )
        self.base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self.timeout = timeout

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> dict[str, Any]:
        data = (
            None
            if body is None
            else json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        request = Request(
            self.base_url + path, data=data, method=method, headers=headers
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, UnicodeError, ValueError) as error:
            raise ProviderUnavailableError(
                f"MRMIC Phase 13 request failed: {method} {path}"
            ) from error
        if not isinstance(result, dict):
            raise ProviderUnavailableError(
                f"MRMIC Phase 13 response was not an object: {method} {path}"
            )
        if self._bearer_token in json.dumps(
            result, ensure_ascii=False, sort_keys=True
        ):
            raise ProviderUnavailableError(
                "MRMIC Phase 13 response contained credential material"
            )
        return result

    def get_capabilities(self) -> dict[str, Any]:
        return self._request_json("/api/capabilities")

    def project_portal(
        self,
        binding: ResourceBinding,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        z_index: int = 20,
        projection_mode: str = "native_resource_portal_v1",
    ) -> dict[str, Any]:
        if projection_mode != "native_resource_portal_v1":
            raise IntegrationContractError(
                "unsupported_phase13_projection_mode", projection_mode
            )
        decision = negotiate_mrmic(self.get_capabilities())
        if decision.status != "compatible":
            raise IntegrationContractError(
                "mrmic_profile_incompatible", ",".join(decision.reason_codes)
            )
        state = self._request_json("/api/state")
        try:
            canvas_id = str(state["canvas"]["id"])
            canvas_revision = int(state["canvas"]["revision"])
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderUnavailableError(
                "MRMIC Phase 13 state response lacked canvas identity or revision"
            ) from error
        portal = build_native_portal(
            binding,
            canvas_id=canvas_id,
            object_id=new_id("portal"),
            geometry={
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "zIndex": z_index,
            },
            now=now_iso(),
        )
        transaction = {
            "id": new_id("pmwtx"),
            "canvasId": canvas_id,
            "actor": {"actorType": "system", "actorId": "pmw-client-claim"},
            "intent": "Project a non-owning PMW resource portal",
            "expectedOutcome": "Create one native resource portal",
            "preconditions": [
                {
                    "type": "canvas_revision",
                    "targetId": canvas_id,
                    "expected": canvas_revision,
                }
            ],
            "operations": [{"op": "create_object", "object": portal}],
            "mode": "direct",
            "createdAt": now_iso(),
            "idempotencyKey": f"pmw-native-portal:{binding.binding_id}",
        }
        response = self._request_json(
            "/api/transaction",
            method="POST",
            body=transaction,
            authenticated=True,
        )
        return {
            "canvas_object_id": portal["id"],
            "canvas_id": portal["canvasId"],
            "projection_mode": "native_resource_portal_v1",
            "provider_result": response,
        }
