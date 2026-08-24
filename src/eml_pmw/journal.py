\
from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Any
from .errors import IdentityConflictError, ResourceConflictError
from .ids import new_id
from .models import SemanticAgent, ProviderBinding, PMWWorkspace, PMWTask, ResourceBinding, DecisionReceipt, now_iso

class FabricJournal:
    # Durable PMW state. Tables are prefixed so it can safely share the Herdr Bridge SQLite file.
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self._migrate()

    def close(self): self.conn.close()

    def _migrate(self):
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS pmw_semantic_agents(
          semantic_agent_id TEXT PRIMARY KEY,
          kind TEXT NOT NULL CHECK(kind IN ('human','ai','system')),
          display_name TEXT NOT NULL,
          role TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pmw_agent_bindings(
          binding_id TEXT PRIMARY KEY,
          semantic_agent_id TEXT NOT NULL REFERENCES pmw_semantic_agents(semantic_agent_id),
          provider TEXT NOT NULL,
          binding_type TEXT NOT NULL,
          provider_resource_id TEXT NOT NULL,
          verified INTEGER NOT NULL CHECK(verified IN (0,1)),
          native_session_id TEXT,
          metadata_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(provider,binding_type,provider_resource_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pmw_agent_bindings_agent ON pmw_agent_bindings(semantic_agent_id,provider);
        CREATE TABLE IF NOT EXISTS pmw_workspaces(
          pmw_workspace_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          visual_provider TEXT NOT NULL,
          visual_workspace_id TEXT,
          visual_canvas_id TEXT,
          created_by TEXT NOT NULL REFERENCES pmw_semantic_agents(semantic_agent_id),
          metadata_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pmw_tasks(
          pmw_task_id TEXT PRIMARY KEY,
          pmw_workspace_id TEXT NOT NULL REFERENCES pmw_workspaces(pmw_workspace_id),
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          created_by TEXT NOT NULL REFERENCES pmw_semantic_agents(semantic_agent_id),
          assigned_to_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pmw_resource_bindings(
          binding_id TEXT PRIMARY KEY,
          pmw_workspace_id TEXT NOT NULL REFERENCES pmw_workspaces(pmw_workspace_id),
          provider TEXT NOT NULL,
          resource_kind TEXT NOT NULL,
          provider_resource_id TEXT NOT NULL,
          display_mode TEXT NOT NULL,
          interaction_mode TEXT NOT NULL,
          owner_semantic_agent_id TEXT REFERENCES pmw_semantic_agents(semantic_agent_id),
          pmw_task_id TEXT REFERENCES pmw_tasks(pmw_task_id),
          canvas_object_id TEXT,
          projection_mode TEXT NOT NULL,
          state TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          revision INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(pmw_workspace_id,provider,resource_kind,provider_resource_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pmw_resources_workspace ON pmw_resource_bindings(pmw_workspace_id,provider);
        CREATE TABLE IF NOT EXISTS pmw_decision_receipts(
          receipt_id TEXT PRIMARY KEY,
          semantic_agent_id TEXT NOT NULL REFERENCES pmw_semantic_agents(semantic_agent_id),
          pmw_workspace_id TEXT NOT NULL REFERENCES pmw_workspaces(pmw_workspace_id),
          pmw_task_id TEXT REFERENCES pmw_tasks(pmw_task_id),
          decision TEXT NOT NULL CHECK(decision IN ('ACK','NO_ACTION','ACTION','ERROR')),
          risk_level TEXT,
          provider TEXT,
          provider_resource_id TEXT,
          evidence_refs_json TEXT NOT NULL,
          note TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pmw_provenance_refs(
          provenance_id TEXT PRIMARY KEY,
          event_type TEXT NOT NULL,
          semantic_agent_id TEXT,
          pmw_workspace_id TEXT,
          pmw_task_id TEXT,
          provider TEXT,
          provider_resource_id TEXT,
          evidence_refs_json TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        ''')

    def upsert_agent(self, semantic_agent_id:str, *, kind:str, display_name:str|None=None, role:str|None=None) -> SemanticAgent:
        now=now_iso(); row=self.conn.execute('SELECT * FROM pmw_semantic_agents WHERE semantic_agent_id=?',(semantic_agent_id,)).fetchone()
        created = row['created_at'] if row else now
        existing_kind = row['kind'] if row else kind
        if row and existing_kind != kind:
            raise IdentityConflictError(f'kind is immutable for {semantic_agent_id}: {existing_kind} != {kind}')
        self.conn.execute('''INSERT INTO pmw_semantic_agents(semantic_agent_id,kind,display_name,role,created_at,updated_at)
          VALUES(?,?,?,?,?,?) ON CONFLICT(semantic_agent_id) DO UPDATE SET display_name=excluded.display_name,role=excluded.role,updated_at=excluded.updated_at''',
          (semantic_agent_id,kind,display_name or semantic_agent_id,role,created,now))
        return self.get_agent(semantic_agent_id)

    def get_agent(self, semantic_agent_id:str) -> SemanticAgent|None:
        r=self.conn.execute('SELECT * FROM pmw_semantic_agents WHERE semantic_agent_id=?',(semantic_agent_id,)).fetchone()
        return None if not r else SemanticAgent(r['semantic_agent_id'],r['kind'],r['display_name'],r['role'],r['created_at'],r['updated_at'])

    def list_agents(self):
        return [self.get_agent(r['semantic_agent_id']).to_dict() for r in self.conn.execute('SELECT semantic_agent_id FROM pmw_semantic_agents ORDER BY semantic_agent_id')]

    def bind_agent(self, semantic_agent_id:str, *, provider:str, binding_type:str, provider_resource_id:str, verified:bool,
                   native_session_id:str|None=None, metadata:dict[str,Any]|None=None) -> ProviderBinding:
        if self.get_agent(semantic_agent_id) is None: raise KeyError(f'unknown semantic agent: {semantic_agent_id}')
        existing=self.conn.execute('SELECT * FROM pmw_agent_bindings WHERE provider=? AND binding_type=? AND provider_resource_id=?',
                                   (provider,binding_type,provider_resource_id)).fetchone()
        now=now_iso()
        if existing and existing['semantic_agent_id'] != semantic_agent_id:
            raise IdentityConflictError(f'provider binding already belongs to {existing["semantic_agent_id"]}')
        bid=existing['binding_id'] if existing else new_id('abind'); created=existing['created_at'] if existing else now
        self.conn.execute('''INSERT INTO pmw_agent_bindings(binding_id,semantic_agent_id,provider,binding_type,provider_resource_id,verified,native_session_id,metadata_json,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(binding_id) DO UPDATE SET semantic_agent_id=excluded.semantic_agent_id,verified=excluded.verified,native_session_id=excluded.native_session_id,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at''',
          (bid,semantic_agent_id,provider,binding_type,provider_resource_id,1 if verified else 0,native_session_id,json.dumps(metadata or {},ensure_ascii=False,sort_keys=True),created,now))
        return self.get_binding(bid)

    def get_binding(self,binding_id:str)->ProviderBinding|None:
        r=self.conn.execute('SELECT * FROM pmw_agent_bindings WHERE binding_id=?',(binding_id,)).fetchone()
        if not r:return None
        return ProviderBinding(r['binding_id'],r['semantic_agent_id'],r['provider'],r['binding_type'],r['provider_resource_id'],bool(r['verified']),r['native_session_id'],json.loads(r['metadata_json']),r['created_at'],r['updated_at'])

    def resolve_principal(self, *, provider:str,binding_type:str,provider_resource_id:str, require_verified:bool=True) -> str|None:
        r=self.conn.execute('SELECT semantic_agent_id,verified FROM pmw_agent_bindings WHERE provider=? AND binding_type=? AND provider_resource_id=?',
                            (provider,binding_type,provider_resource_id)).fetchone()
        if not r or (require_verified and not bool(r['verified'])): return None
        return r['semantic_agent_id']

    def list_bindings(self,semantic_agent_id:str|None=None):
        q='SELECT binding_id FROM pmw_agent_bindings'; args=()
        if semantic_agent_id: q+=' WHERE semantic_agent_id=?'; args=(semantic_agent_id,)
        q+=' ORDER BY provider,binding_type,provider_resource_id'
        return [self.get_binding(r['binding_id']).to_dict() for r in self.conn.execute(q,args)]

    def create_workspace(self,title:str,created_by:str,*,pmw_workspace_id:str|None=None,visual_provider:str='mrmic',visual_workspace_id:str|None=None,visual_canvas_id:str|None=None,metadata:dict[str,Any]|None=None)->PMWWorkspace:
        if self.get_agent(created_by) is None: raise KeyError(f'unknown creator: {created_by}')
        wid=pmw_workspace_id or new_id('pws'); now=now_iso()
        self.conn.execute('INSERT INTO pmw_workspaces VALUES(?,?,?,?,?,?,?,?,?)',(wid,title,visual_provider,visual_workspace_id,visual_canvas_id,created_by,json.dumps(metadata or {},ensure_ascii=False,sort_keys=True),now,now))
        return self.get_workspace(wid)

    def get_workspace(self,wid:str)->PMWWorkspace|None:
        r=self.conn.execute('SELECT * FROM pmw_workspaces WHERE pmw_workspace_id=?',(wid,)).fetchone()
        if not r:return None
        return PMWWorkspace(r['pmw_workspace_id'],r['title'],r['visual_provider'],r['visual_workspace_id'],r['visual_canvas_id'],r['created_by'],json.loads(r['metadata_json']),r['created_at'],r['updated_at'])

    def update_workspace_visual_binding(self,wid:str,*,visual_workspace_id:str,visual_canvas_id:str):
        if self.get_workspace(wid) is None: raise KeyError(wid)
        self.conn.execute('UPDATE pmw_workspaces SET visual_workspace_id=?,visual_canvas_id=?,updated_at=? WHERE pmw_workspace_id=?',(visual_workspace_id,visual_canvas_id,now_iso(),wid))
        return self.get_workspace(wid)

    def list_workspaces(self): return [self.get_workspace(r['pmw_workspace_id']).to_dict() for r in self.conn.execute('SELECT pmw_workspace_id FROM pmw_workspaces ORDER BY created_at')]

    def create_task(self,wid:str,title:str,created_by:str,*,assigned_to:list[str]|None=None,status:str='pending',metadata:dict[str,Any]|None=None,pmw_task_id:str|None=None)->PMWTask:
        if self.get_workspace(wid) is None: raise KeyError(f'unknown workspace: {wid}')
        if self.get_agent(created_by) is None: raise KeyError(f'unknown creator: {created_by}')
        assigned=assigned_to or []
        for a in assigned:
            if self.get_agent(a) is None: raise KeyError(f'unknown assignee: {a}')
        tid=pmw_task_id or new_id('ptask'); now=now_iso()
        self.conn.execute('INSERT INTO pmw_tasks VALUES(?,?,?,?,?,?,?,?,?)',(tid,wid,title,status,created_by,json.dumps(assigned,ensure_ascii=False),json.dumps(metadata or {},ensure_ascii=False,sort_keys=True),now,now))
        return self.get_task(tid)

    def get_task(self,tid:str)->PMWTask|None:
        r=self.conn.execute('SELECT * FROM pmw_tasks WHERE pmw_task_id=?',(tid,)).fetchone()
        if not r:return None
        return PMWTask(r['pmw_task_id'],r['pmw_workspace_id'],r['title'],r['status'],r['created_by'],json.loads(r['assigned_to_json']),json.loads(r['metadata_json']),r['created_at'],r['updated_at'])

    def bind_resource(self,wid:str,*,provider:str,resource_kind:str,provider_resource_id:str,display_mode:str='snapshot',interaction_mode:str='inspect',owner_semantic_agent_id:str|None=None,pmw_task_id:str|None=None,canvas_object_id:str|None=None,projection_mode:str='unprojected',state:str='bound',metadata:dict[str,Any]|None=None)->ResourceBinding:
        if self.get_workspace(wid) is None: raise KeyError(wid)
        if owner_semantic_agent_id and self.get_agent(owner_semantic_agent_id) is None: raise KeyError(owner_semantic_agent_id)
        if pmw_task_id:
            t=self.get_task(pmw_task_id)
            if not t or t.pmw_workspace_id != wid: raise ResourceConflictError('task must belong to resource workspace')
        existing=self.conn.execute('SELECT binding_id FROM pmw_resource_bindings WHERE pmw_workspace_id=? AND provider=? AND resource_kind=? AND provider_resource_id=?',(wid,provider,resource_kind,provider_resource_id)).fetchone()
        if existing: return self.get_resource(existing['binding_id'])
        bid=new_id('rbind'); now=now_iso()
        self.conn.execute('''INSERT INTO pmw_resource_bindings(binding_id,pmw_workspace_id,provider,resource_kind,provider_resource_id,display_mode,interaction_mode,owner_semantic_agent_id,pmw_task_id,canvas_object_id,projection_mode,state,metadata_json,revision,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(bid,wid,provider,resource_kind,provider_resource_id,display_mode,interaction_mode,owner_semantic_agent_id,pmw_task_id,canvas_object_id,projection_mode,state,json.dumps(metadata or {},ensure_ascii=False,sort_keys=True),0,now,now))
        return self.get_resource(bid)

    def get_resource(self,bid:str)->ResourceBinding|None:
        r=self.conn.execute('SELECT * FROM pmw_resource_bindings WHERE binding_id=?',(bid,)).fetchone()
        if not r:return None
        return ResourceBinding(r['binding_id'],r['pmw_workspace_id'],r['provider'],r['resource_kind'],r['provider_resource_id'],r['display_mode'],r['interaction_mode'],r['owner_semantic_agent_id'],r['pmw_task_id'],r['canvas_object_id'],r['projection_mode'],r['state'],json.loads(r['metadata_json']),r['revision'],r['created_at'],r['updated_at'])

    def update_resource_projection(self,bid:str,*,canvas_object_id:str,projection_mode:str,state:str='projected_snapshot',metadata_patch:dict[str,Any]|None=None)->ResourceBinding:
        r=self.get_resource(bid)
        if not r: raise KeyError(bid)
        meta=dict(r.metadata); meta.update(metadata_patch or {})
        self.conn.execute('''UPDATE pmw_resource_bindings SET canvas_object_id=?,projection_mode=?,state=?,metadata_json=?,revision=revision+1,updated_at=? WHERE binding_id=?''',(canvas_object_id,projection_mode,state,json.dumps(meta,ensure_ascii=False,sort_keys=True),now_iso(),bid))
        return self.get_resource(bid)

    def list_resources(self,wid:str):
        return [self.get_resource(r['binding_id']).to_dict() for r in self.conn.execute('SELECT binding_id FROM pmw_resource_bindings WHERE pmw_workspace_id=? ORDER BY created_at',(wid,))]

    def record_decision(self,*,semantic_agent_id:str,pmw_workspace_id:str,decision:str,pmw_task_id:str|None=None,risk_level:str|None=None,provider:str|None=None,provider_resource_id:str|None=None,evidence_refs:list[str]|None=None,note:str='')->DecisionReceipt:
        if decision not in {'ACK','NO_ACTION','ACTION','ERROR'}: raise ValueError('invalid decision')
        if self.get_agent(semantic_agent_id) is None: raise KeyError(semantic_agent_id)
        if self.get_workspace(pmw_workspace_id) is None: raise KeyError(pmw_workspace_id)
        rid=new_id('receipt'); now=now_iso()
        self.conn.execute('INSERT INTO pmw_decision_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,semantic_agent_id,pmw_workspace_id,pmw_task_id,decision,risk_level,provider,provider_resource_id,json.dumps(evidence_refs or [],ensure_ascii=False),note,now))
        return DecisionReceipt(rid,semantic_agent_id,pmw_workspace_id,pmw_task_id,decision,risk_level,provider,provider_resource_id,evidence_refs or [],note,now)

    def list_decisions(self,wid:str):
        rows=self.conn.execute('SELECT * FROM pmw_decision_receipts WHERE pmw_workspace_id=? ORDER BY created_at',(wid,)).fetchall()
        return [dict(r) | {'evidence_refs':json.loads(r['evidence_refs_json'])} for r in rows]

    def record_provenance(self,event_type:str,payload:dict[str,Any],*,semantic_agent_id:str|None=None,pmw_workspace_id:str|None=None,pmw_task_id:str|None=None,provider:str|None=None,provider_resource_id:str|None=None,evidence_refs:list[str]|None=None)->str:
        pid=new_id('prov'); self.conn.execute('INSERT INTO pmw_provenance_refs VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,event_type,semantic_agent_id,pmw_workspace_id,pmw_task_id,provider,provider_resource_id,json.dumps(evidence_refs or [],ensure_ascii=False),json.dumps(payload,ensure_ascii=False,sort_keys=True),now_iso())); return pid
