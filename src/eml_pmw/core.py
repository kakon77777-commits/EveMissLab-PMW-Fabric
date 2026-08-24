from __future__ import annotations
from typing import Any
from .journal import FabricJournal
from .presence import PresenceHub
from .models import ResourceBinding
from .adapters.herdr_bridge import HerdrBridgeImportAdapter

class PMWFabric:
    def __init__(self,journal:FabricJournal,presence:PresenceHub|None=None): self.journal=journal; self.presence=presence or PresenceHub()

    def import_herdr_agent(self,semantic_agent_id:str,adapter:HerdrBridgeImportAdapter,*,kind:str='ai') -> dict[str,Any]:
        record=adapter.read_agent(semantic_agent_id); runtime=record['runtime_binding']
        agent=self.journal.upsert_agent(semantic_agent_id,kind=kind,display_name=record.get('display_name') or semantic_agent_id,role=record.get('role'))
        native=runtime.get('native_session_ref') or {}
        native_id=native.get('value') if isinstance(native,dict) else None
        binding=self.journal.bind_agent(semantic_agent_id,provider='herdr',binding_type='agent_session',provider_resource_id=runtime['agent_target'],verified=True,native_session_id=native_id,metadata={'bridge_binding_id':runtime.get('binding_id'),'terminal_id':runtime.get('terminal_id'),'pane_id':runtime.get('pane_id'),'workspace_id':runtime.get('workspace_id'),'runtime_epoch_id':runtime.get('runtime_epoch_id'),'agent_kind':runtime.get('agent_kind')})
        return {'agent':agent.to_dict(),'binding':binding.to_dict()}

    def project_resource(self,binding_id:str,visual_adapter,*,x:float,y:float,width:float,height:float,z_index:int=20,projection_mode:str='compat_frame_v0')->ResourceBinding:
        binding=self.journal.get_resource(binding_id)
        if not binding: raise KeyError(binding_id)
        result=visual_adapter.project_portal(binding,x=x,y=y,width=width,height=height,z_index=z_index,projection_mode=projection_mode)
        updated=self.journal.update_resource_projection(binding_id,canvas_object_id=result['canvas_object_id'],projection_mode=result['projection_mode'],state='projected_live' if binding.display_mode=='live' else 'projected_snapshot',metadata_patch={'visual_canvas_id':result.get('canvas_id'),'projection_result':result.get('provider_result',{})})
        self.journal.record_provenance('resource.projected',updated.to_dict(),semantic_agent_id=binding.owner_semantic_agent_id,pmw_workspace_id=binding.pmw_workspace_id,pmw_task_id=binding.pmw_task_id,provider=binding.provider,provider_resource_id=binding.provider_resource_id,evidence_refs=[f'canvas-object:{updated.canvas_object_id}'])
        return updated
