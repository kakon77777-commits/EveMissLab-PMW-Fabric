# MRMIC Phase 13 Patch Contract — PMW Visual World Integration

Grounding baseline: `MRMIC_NVCL main@6606b54532c0f327206e7c021120370044b6e0ff`.

## Required changes

1. Extend `CanvasObjectType` with `resource_portal`.
2. Extend structured portal content/metadata with a provider-neutral resource reference.
3. Render a portal frame/card in the web UI without making Canvas canonical owner of the provider resource.
4. Add an authenticated principal -> semantic identity resolver for WebSocket presence.
5. Do not accept `actorType` / `actorId` from a peer as identity proof.
6. Preserve current state-vector ordering, revision preconditions, idempotency and event hashes.
7. Add a live-overlay host contract; do not put Electron `<webview>` inside SVG `foreignObject`.
8. Provider overlays must separate visible/mounted/focused/control-owner state.

## Compatibility bridge

Before Phase 13 lands, PMW Fabric can project a resource as the existing `frame` type with metadata:

```json
{
  "role": "pmw-resource-portal",
  "projectionMode": "compat_frame_v0",
  "provider": "tandem",
  "resourceKind": "browser_tab",
  "providerResourceId": "tab-2"
}
```

This compatibility object is explicitly a visual projection only.

## Security gate

Live agent presence MUST remain disabled in the external PMW adapter until the WebSocket connection is associated with an authenticated binding. Phase 12's message payload is structurally capable of `actorType: agent`, but structural validity is not authentication.
