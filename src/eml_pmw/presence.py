from __future__ import annotations
from .models import PresenceEnvelope, now_iso

class PresenceHub:
    """Ephemeral presence. Deliberately not persisted as durable PMW state."""
    def __init__(self): self._items: dict[tuple[str,str], PresenceEnvelope] = {}

    def set(self, *, semantic_agent_id:str, pmw_workspace_id:str, provider:str, cursor=None, viewport=None, selected_object_ids=None, task=None) -> PresenceEnvelope:
        item=PresenceEnvelope(semantic_agent_id,pmw_workspace_id,provider,cursor,viewport,list(selected_object_ids or []),task,now_iso(),True)
        self._items[(pmw_workspace_id,semantic_agent_id)]=item
        return item

    def remove(self,pmw_workspace_id:str,semantic_agent_id:str)->bool:
        return self._items.pop((pmw_workspace_id,semantic_agent_id),None) is not None

    def snapshot(self,pmw_workspace_id:str)->list[dict]:
        return [v.to_dict() for (w,_),v in sorted(self._items.items()) if w==pmw_workspace_id]
