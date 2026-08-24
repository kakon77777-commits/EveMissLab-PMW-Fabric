# Security boundaries

1. Semantic identity is canonical; provider IDs are bindings.
2. A provider binding is immutable across semantic identities unless explicitly removed through a future administrative action.
3. Unverified bindings cannot resolve as authenticated principals.
4. Canvas projection deletion is non-destructive by default.
5. MRMIC Phase 12 agent-presence injection is refused because payload identity is not authentication.
6. Herdr `blocked` authority rule remains unchanged in the embedded bridge.
7. Tandem medium/high-risk approval remains provider-side authority, not Canvas UI state.
8. A portal drag/drop gesture expresses intent; it does not itself execute a privileged provider action.
