from __future__ import annotations
from pathlib import Path
import tempfile, re
from eml_bridge.core import BridgeEngine
from eml_bridge.journal import SQLiteJournal
from eml_bridge.mock_herdr import MockHerdrAdapter
from .journal import FabricJournal
from .core import PMWFabric
from .adapters.herdr_bridge import HerdrBridgeImportAdapter
from .adapters.mock_visual import MockVisualAdapter


def _response(target:str,prompt:str)->str:
    m=re.search(r'(?m)^EML_REPLY_[A-Za-z0-9_-]+$',prompt)
    return f'ok from {target}\n{m.group(0)}\n' if m else f'ok from {target}\n'

def run_demo(directory:Path)->dict:
    directory.mkdir(parents=True,exist_ok=True); db=directory/'pmw.sqlite3'
    bridge_j=SQLiteJournal(db); mock=MockHerdrAdapter(_response); mock.add_agent('claude-main',kind='claude'); mock.add_agent('codex-reviewer',kind='codex')
    engine=BridgeEngine(journal=bridge_j,herdr=mock,prompt_effect_timeout_ms=20,poll_interval_ms=1)
    claude='agent://evemisslab/research/claude-main'; codex='agent://evemisslab/research/codex-reviewer'
    engine.bind_agent(claude,'claude-main'); engine.bind_agent(codex,'codex-reviewer'); bridge_j.close()

    j=FabricJournal(db); f=PMWFabric(j)
    f.journal.upsert_agent('user:neo',kind='human',display_name='Neo.K',role='workspace owner')
    hb=HerdrBridgeImportAdapter(db); f.import_herdr_agent(claude,hb); f.import_herdr_agent(codex,hb)
    ws=f.journal.create_workspace('Shared Research Canvas','user:neo',pmw_workspace_id='pmw-ws-demo',visual_provider='mrmic',visual_workspace_id='workspace-root',visual_canvas_id='canvas-root')
    task=f.journal.create_task(ws.pmw_workspace_id,'Independent browser verification','user:neo',assigned_to=[claude,codex],pmw_task_id='pmw-task-demo')
    r1=f.journal.bind_resource(ws.pmw_workspace_id,provider='tandem',resource_kind='browser_tab',provider_resource_id='tab-claude',display_mode='live',interaction_mode='control',owner_semantic_agent_id=claude,pmw_task_id=task.pmw_task_id)
    r2=f.journal.bind_resource(ws.pmw_workspace_id,provider='tandem',resource_kind='browser_tab',provider_resource_id='tab-codex',display_mode='live',interaction_mode='control',owner_semantic_agent_id=codex,pmw_task_id=task.pmw_task_id)
    r3=f.journal.bind_resource(ws.pmw_workspace_id,provider='herdr',resource_kind='terminal_agent',provider_resource_id='claude-main',display_mode='summary',interaction_mode='inspect',owner_semantic_agent_id=claude,pmw_task_id=task.pmw_task_id)
    r4=f.journal.bind_resource(ws.pmw_workspace_id,provider='herdr',resource_kind='terminal_agent',provider_resource_id='codex-reviewer',display_mode='summary',interaction_mode='inspect',owner_semantic_agent_id=codex,pmw_task_id=task.pmw_task_id)
    visual=MockVisualAdapter()
    for idx,r in enumerate([r1,r2,r3,r4]): f.project_resource(r.binding_id,visual,x=80+idx*260,y=120,width=220,height=150,projection_mode='native_resource_portal')
    f.presence.set(semantic_agent_id='user:neo',pmw_workspace_id=ws.pmw_workspace_id,provider='mrmic',cursor={'x':20,'y':20},task='observing')
    f.presence.set(semantic_agent_id=claude,pmw_workspace_id=ws.pmw_workspace_id,provider='mrmic',cursor={'x':120,'y':180},task='research')
    f.presence.set(semantic_agent_id=codex,pmw_workspace_id=ws.pmw_workspace_id,provider='mrmic',cursor={'x':640,'y':180},task='verify')
    receipt=f.journal.record_decision(semantic_agent_id=codex,pmw_workspace_id=ws.pmw_workspace_id,pmw_task_id=task.pmw_task_id,decision='ACTION',provider='tandem',provider_resource_id='tab-codex',evidence_refs=['canvas-object:'+visual.portals[1]['canvas_object_id']],note='Independent verification completed')
    out={'workspace':ws.to_dict(),'task':task.to_dict(),'agents':f.journal.list_agents(),'bindings':f.journal.list_bindings(),'resources':f.journal.list_resources(ws.pmw_workspace_id),'presence':f.presence.snapshot(ws.pmw_workspace_id),'portal_count':len(visual.portals),'decision':receipt.to_dict()}
    j.close(); return out
