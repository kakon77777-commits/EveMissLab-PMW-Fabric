from __future__ import annotations

from typing import Any

from eml_pmw.models import ResourceBinding


def build_native_portal(
    binding: ResourceBinding,
    *,
    canvas_id: str,
    object_id: str,
    geometry: dict[str, float | int],
    now: str,
) -> dict[str, Any]:
    transform = {
        "x": geometry["x"],
        "y": geometry["y"],
        "width": geometry["width"],
        "height": geometry["height"],
        "rotation": 0,
        "scaleX": 1,
        "scaleY": 1,
        "zIndex": geometry["zIndex"],
    }
    return {
        "id": object_id,
        "canvasId": canvas_id,
        "type": "resource_portal",
        "transform": transform,
        "style": {},
        "content": {"text": f"{binding.provider}:{binding.resource_kind}"},
        "childIds": [],
        "bindings": [],
        "metadata": {
            "portalSchema": "native_resource_portal_v1",
            "portal": {
                "portalId": binding.binding_id,
                "pmwWorkspaceId": binding.pmw_workspace_id,
                "pmwTaskId": binding.pmw_task_id,
                "provider": binding.provider,
                "resourceKind": binding.resource_kind,
                "providerResourceId": binding.provider_resource_id,
                "displayMode": binding.display_mode,
                "interactionMode": binding.interaction_mode,
            },
        },
        "createdBy": {"actorType": "system", "actorId": "pmw-client-claim"},
        "createdAt": now,
        "updatedAt": now,
        "revision": 0,
    }
