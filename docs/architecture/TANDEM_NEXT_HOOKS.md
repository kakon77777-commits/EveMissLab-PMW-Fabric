# Tandem next integration hooks

Baseline: PR #2 `pmw-mainline/join-authority-i4@0628a03d7e0bec5f5a081ae64739418d9a320129`.

Minimal hooks only:

- stable resource descriptor for tab/workspace/state-node;
- preview/snapshot endpoint for a tab portal;
- split `visible` from `focused` in renderer/runtime state;
- explicit live-surface budget;
- trusted semantic binding metadata linked to the authenticated Tandem principal;
- retain TabLockManager as browser-specific PMW ISOLATE;
- retain Handoff/Authority/DecisionReceipt semantics.

Do not move PMW global identity into Tandem. Tandem remains a browser provider.
