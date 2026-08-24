from __future__ import annotations
import argparse, json, os
from pathlib import Path
from .journal import FabricJournal
from .core import PMWFabric
from .adapters.herdr_bridge import HerdrBridgeImportAdapter
from .adapters.mrmic import MRMICHTTPAdapter
from .demo import run_demo

def _print(v): print(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True))
def _j(args): return FabricJournal(args.db)

def cmd_agent_add(a):
    j=_j(a)
    try:_print(j.upsert_agent(a.semantic_id,kind=a.kind,display_name=a.display_name,role=a.role).to_dict());return 0
    finally:j.close()
def cmd_bind(a):
    j=_j(a)
    try:_print(j.bind_agent(a.semantic_id,provider=a.provider,binding_type=a.binding_type,provider_resource_id=a.provider_resource_id,verified=a.verified,native_session_id=a.native_session_id).to_dict());return 0
    finally:j.close()
def cmd_import_herdr(a):
    j=_j(a)
    try:_print(PMWFabric(j).import_herdr_agent(a.semantic_id,HerdrBridgeImportAdapter(a.bridge_db)));return 0
    finally:j.close()
def cmd_workspace_create(a):
    j=_j(a)
    try:_print(j.create_workspace(a.title,a.created_by,pmw_workspace_id=a.id,visual_provider='mrmic',visual_workspace_id=a.visual_workspace_id,visual_canvas_id=a.visual_canvas_id).to_dict());return 0
    finally:j.close()
def cmd_task_create(a):
    j=_j(a)
    try:_print(j.create_task(a.workspace,a.title,a.created_by,assigned_to=a.assigned_to,pmw_task_id=a.id).to_dict());return 0
    finally:j.close()
def cmd_resource_bind(a):
    j=_j(a)
    try:_print(j.bind_resource(a.workspace,provider=a.provider,resource_kind=a.kind,provider_resource_id=a.resource_id,display_mode=a.display,interaction_mode=a.interaction,owner_semantic_agent_id=a.owner,pmw_task_id=a.task).to_dict());return 0
    finally:j.close()
def cmd_project_mrmic(a):
    j=_j(a)
    try:_print(PMWFabric(j).project_resource(a.binding_id,MRMICHTTPAdapter(a.url),x=a.x,y=a.y,width=a.width,height=a.height,z_index=a.z,projection_mode=a.projection_mode).to_dict());return 0
    finally:j.close()
def cmd_show(a):
    j=_j(a)
    try:
        if a.what=='agents':_print(j.list_agents())
        elif a.what=='bindings':_print(j.list_bindings())
        elif a.what=='workspaces':_print(j.list_workspaces())
        elif a.what=='resources':_print(j.list_resources(a.workspace))
        return 0
    finally:j.close()
def cmd_demo(a): _print(run_demo(Path(a.demo_dir))); return 0

def build_parser():
    p=argparse.ArgumentParser(prog='eml-pmw',description='EveMissLab Canvas-first PMW Fabric Runtime MVP v0.1')
    root=Path(os.environ.get('EML_PMW_HOME',str(Path.home()/'.evemisslab'/'pmw-fabric')))
    p.add_argument('--db',default=str(root/'pmw.sqlite3'))
    s=p.add_subparsers(dest='cmd',required=True)
    x=s.add_parser('agent-add');x.add_argument('semantic_id');x.add_argument('--kind',choices=['human','ai','system'],required=True);x.add_argument('--display-name');x.add_argument('--role');x.set_defaults(func=cmd_agent_add)
    x=s.add_parser('bind');x.add_argument('semantic_id');x.add_argument('provider');x.add_argument('binding_type');x.add_argument('provider_resource_id');x.add_argument('--verified',action='store_true');x.add_argument('--native-session-id');x.set_defaults(func=cmd_bind)
    x=s.add_parser('import-herdr');x.add_argument('semantic_id');x.add_argument('--bridge-db',required=True);x.set_defaults(func=cmd_import_herdr)
    x=s.add_parser('workspace-create');x.add_argument('title');x.add_argument('--created-by',required=True);x.add_argument('--id');x.add_argument('--visual-workspace-id');x.add_argument('--visual-canvas-id');x.set_defaults(func=cmd_workspace_create)
    x=s.add_parser('task-create');x.add_argument('workspace');x.add_argument('title');x.add_argument('--created-by',required=True);x.add_argument('--assigned-to',action='append',default=[]);x.add_argument('--id');x.set_defaults(func=cmd_task_create)
    x=s.add_parser('resource-bind');x.add_argument('workspace');x.add_argument('provider');x.add_argument('kind');x.add_argument('resource_id');x.add_argument('--display',default='snapshot');x.add_argument('--interaction',default='inspect');x.add_argument('--owner');x.add_argument('--task');x.set_defaults(func=cmd_resource_bind)
    x=s.add_parser('project-mrmic');x.add_argument('binding_id');x.add_argument('--url',default='http://127.0.0.1:4173');x.add_argument('--x',type=float,default=100);x.add_argument('--y',type=float,default=100);x.add_argument('--width',type=float,default=600);x.add_argument('--height',type=float,default=400);x.add_argument('--z',type=int,default=20);x.add_argument('--projection-mode',default='compat_frame_v0',choices=['compat_frame_v0','native_resource_portal']);x.set_defaults(func=cmd_project_mrmic)
    x=s.add_parser('show');x.add_argument('what',choices=['agents','bindings','workspaces','resources']);x.add_argument('--workspace');x.set_defaults(func=cmd_show)
    x=s.add_parser('demo');x.add_argument('--demo-dir',default='run/pmw-demo');x.set_defaults(func=cmd_demo)
    return p

def main(argv=None):
    a=build_parser().parse_args(argv);return int(a.func(a))
