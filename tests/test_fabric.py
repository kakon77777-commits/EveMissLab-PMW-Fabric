from __future__ import annotations
import tempfile, unittest, re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eml_pmw.journal import FabricJournal
from eml_pmw.core import PMWFabric
from eml_pmw.presence import PresenceHub
from eml_pmw.errors import IdentityConflictError, ResourceConflictError, UnsafeIntegrationError, UnsupportedProjectionError
from eml_pmw.adapters.mock_visual import MockVisualAdapter
from eml_pmw.adapters.mrmic import MRMICHTTPAdapter
from eml_pmw.demo import run_demo

class FabricTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.j=FabricJournal(Path(self.tmp.name)/'x.sqlite3')
        self.j.upsert_agent('user:neo',kind='human',display_name='Neo')
        self.j.upsert_agent('agent:claude',kind='ai',display_name='Claude')
        self.ws=self.j.create_workspace('W','user:neo',pmw_workspace_id='w1')
    def tearDown(self): self.j.close();self.tmp.cleanup()
    def test_binding_cannot_move_between_semantic_identities(self):
        self.j.bind_agent('agent:claude',provider='tandem',binding_type='authenticated_actor',provider_resource_id='agent:abcd',verified=True)
        self.j.upsert_agent('agent:codex',kind='ai',display_name='Codex')
        with self.assertRaises(IdentityConflictError): self.j.bind_agent('agent:codex',provider='tandem',binding_type='authenticated_actor',provider_resource_id='agent:abcd',verified=True)
    def test_unverified_principal_does_not_resolve(self):
        self.j.bind_agent('agent:claude',provider='external',binding_type='session',provider_resource_id='s1',verified=False)
        self.assertIsNone(self.j.resolve_principal(provider='external',binding_type='session',provider_resource_id='s1'))
    def test_resource_task_must_share_workspace(self):
        t=self.j.create_task('w1','t','user:neo')
        w2=self.j.create_workspace('W2','user:neo',pmw_workspace_id='w2')
        with self.assertRaises(ResourceConflictError): self.j.bind_resource(w2.pmw_workspace_id,provider='tandem',resource_kind='browser_tab',provider_resource_id='x',pmw_task_id=t.pmw_task_id)
    def test_projection_updates_binding_not_provider_identity(self):
        r=self.j.bind_resource('w1',provider='tandem',resource_kind='browser_tab',provider_resource_id='tab-1')
        f=PMWFabric(self.j);v=MockVisualAdapter();u=f.project_resource(r.binding_id,v,x=1,y=2,width=3,height=4,projection_mode='native_resource_portal')
        self.assertEqual(u.provider_resource_id,'tab-1');self.assertTrue(u.canvas_object_id);self.assertEqual(u.revision,1)
    def test_presence_is_ephemeral_and_separate(self):
        h=PresenceHub();h.set(semantic_agent_id='agent:claude',pmw_workspace_id='w1',provider='mrmic',cursor={'x':1,'y':2});self.assertEqual(len(h.snapshot('w1')),1);h.remove('w1','agent:claude');self.assertEqual(h.snapshot('w1'),[])
    def test_phase12_presence_injection_is_refused(self):
        with self.assertRaises(UnsafeIntegrationError): MRMICHTTPAdapter().push_agent_presence()
    def test_phase12_native_portal_requires_patch(self):
        r=self.j.bind_resource('w1',provider='tandem',resource_kind='browser_tab',provider_resource_id='tab-2')
        with self.assertRaises(UnsupportedProjectionError): MRMICHTTPAdapter().project_portal(r,x=0,y=0,width=1,height=1,projection_mode='native_resource_portal')

class DemoTests(unittest.TestCase):
    def test_integrated_demo(self):
        with tempfile.TemporaryDirectory() as d:
            out=run_demo(Path(d));self.assertEqual(out['portal_count'],4);self.assertEqual(len(out['presence']),3);self.assertEqual(out['decision']['decision'],'ACTION');self.assertEqual(len(out['agents']),3)

if __name__=='__main__': unittest.main()

class FakeMRMIC(MRMICHTTPAdapter):
    def __init__(self):
        super().__init__('http://invalid.local'); self.requests=[]
    def _json(self,path,method='GET',body=None):
        self.requests.append((path,method,body))
        if method=='GET' and path=='/api/state': return {'canvas':{'id':'canvas-root','revision':7}}
        if method=='POST' and path=='/api/transaction': return {'ok':True,'revision':8}
        raise AssertionError((path,method))

class MRMICCompatibilityTests(unittest.TestCase):
    def test_compat_frame_is_non_owning_projection_with_revision_precondition(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=FabricJournal(Path(tmp)/'x.sqlite3')
            j.upsert_agent('user:neo',kind='human',display_name='Neo')
            j.create_workspace('W','user:neo',pmw_workspace_id='w1')
            r=j.bind_resource('w1',provider='tandem',resource_kind='browser_tab',provider_resource_id='tab-1')
            a=FakeMRMIC(); result=a.project_portal(r,x=10,y=20,width=300,height=200,projection_mode='compat_frame_v0')
            self.assertEqual(result['projection_mode'],'compat_frame_v0')
            tx=a.requests[-1][2]
            self.assertEqual(tx['preconditions'][0]['expected'],7)
            obj=tx['operations'][0]['object']
            self.assertEqual(obj['type'],'frame')
            self.assertEqual(obj['metadata']['role'],'pmw-resource-portal')
            self.assertEqual(obj['metadata']['providerResourceId'],'tab-1')
            self.assertEqual(obj['createdBy']['actorType'],'system')
            j.close()
