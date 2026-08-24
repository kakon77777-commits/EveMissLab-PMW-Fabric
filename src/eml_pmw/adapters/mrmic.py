from __future__ import annotations
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from uuid import uuid4
from typing import Any
from ..errors import ProviderUnavailableError, UnsupportedProjectionError, UnsafeIntegrationError
from ..models import ResourceBinding, now_iso

class MRMICHTTPAdapter:
    """Adapter for MRMIC/NVCL Phase 12 HTTP surface.

    Phase 12 has no authenticated actor binding on WebSocket presence, so this adapter
    intentionally refuses live agent-presence injection. Portal projection can use the
    current schema's `frame + metadata` compatibility mode until native resource_portal ships.
    """
    def __init__(self,base_url:str='http://127.0.0.1:4173',timeout:float=5.0):
        self.base_url=base_url.rstrip('/'); self.timeout=timeout

    def _json(self,path:str,method:str='GET',body:dict|None=None)->dict[str,Any]:
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        req=Request(self.base_url+path,data=data,method=method,headers={'content-type':'application/json'})
        try:
            with urlopen(req,timeout=self.timeout) as r: return json.loads(r.read().decode('utf-8'))
        except (URLError,HTTPError,OSError,ValueError) as exc:
            raise ProviderUnavailableError(f'MRMIC request failed: {method} {path}: {exc}') from exc

    def get_state(self)->dict[str,Any]: return self._json('/api/state')
    def sync_status(self)->dict[str,Any]: return self._json('/api/sync/status')

    def project_portal(self,binding:ResourceBinding,*,x:float,y:float,width:float,height:float,z_index:int=20,projection_mode:str='compat_frame_v0')->dict[str,Any]:
        if projection_mode=='native_resource_portal':
            raise UnsupportedProjectionError('MRMIC Phase 12 schema does not yet accept resource_portal; apply Phase 13 patch first')
        if projection_mode!='compat_frame_v0': raise UnsupportedProjectionError(projection_mode)
        state=self.get_state(); canvas=state['canvas']; canvas_id=str(canvas['id']); revision=int(canvas['revision'])
        oid='pmw-portal-'+uuid4().hex
        now=now_iso()
        obj={
          'id':oid,'canvasId':canvas_id,'type':'frame',
          'transform':{'x':x,'y':y,'width':width,'height':height,'rotation':0,'scaleX':1,'scaleY':1,'zIndex':z_index},
          'style':{'fill':'#eef2ff','stroke':'#4f46e5','strokeWidth':2,'opacity':1},
          'content':{},'childIds':[],'bindings':[],
          'metadata':{
            'role':'pmw-resource-portal','projectionMode':'compat_frame_v0','provider':binding.provider,
            'resourceKind':binding.resource_kind,'providerResourceId':binding.provider_resource_id,
            'pmwWorkspaceId':binding.pmw_workspace_id,'pmwTaskId':binding.pmw_task_id,
            'resourceBindingId':binding.binding_id,'displayMode':binding.display_mode,
            'interactionMode':binding.interaction_mode,'ownerSemanticAgentId':binding.owner_semantic_agent_id,
          },
          'createdBy':{'actorType':'system','actorId':'pmw-fabric','instanceId':'eml-pmw-v0.1'},
          'createdAt':now,'updatedAt':now,'revision':0,
        }
        tx={
          'id':'pmw-tx-'+uuid4().hex,'canvasId':canvas_id,
          'actor':{'actorType':'system','actorId':'pmw-fabric','instanceId':'eml-pmw-v0.1'},
          'intent':f'Project {binding.provider}:{binding.resource_kind} into shared visual world',
          'expectedOutcome':'Create a non-owning resource projection',
          'preconditions':[{'type':'canvas_revision','targetId':canvas_id,'expected':revision}],
          'operations':[{'op':'create_object','object':obj}],
          'mode':'direct','createdAt':now,'idempotencyKey':f'pmw-portal:{binding.binding_id}',
        }
        result=self._json('/api/transaction','POST',tx)
        return {'canvas_object_id':oid,'canvas_id':canvas_id,'projection_mode':'compat_frame_v0','provider_result':result}

    def push_agent_presence(self,*args,**kwargs):
        raise UnsafeIntegrationError('MRMIC Phase 12 WebSocket presence trusts payload actor identity; authenticated agent presence requires the Phase 13 identity patch')
