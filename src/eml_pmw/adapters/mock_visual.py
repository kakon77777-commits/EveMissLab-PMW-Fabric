from __future__ import annotations
from ..ids import new_id
class MockVisualAdapter:
    def __init__(self): self.portals=[]
    def project_portal(self,binding,*,x,y,width,height,z_index=20,projection_mode='native_resource_portal'):
        oid=new_id('obj'); rec={'canvas_object_id':oid,'canvas_id':'canvas-root','projection_mode':projection_mode,'binding_id':binding.binding_id,'geometry':{'x':x,'y':y,'width':width,'height':height,'z':z_index}}; self.portals.append(rec); return rec
