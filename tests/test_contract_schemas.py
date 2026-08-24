from __future__ import annotations
import json, unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import jsonschema
class SchemaTests(unittest.TestCase):
    def test_schemas_meta_validate(self):
        for p in (ROOT/'schemas').glob('*.json'): jsonschema.Draft202012Validator.check_schema(json.loads(p.read_text(encoding='utf-8')))
    def test_resource_portal_example(self):
        schema=json.loads((ROOT/'schemas/resource-portal.schema.json').read_text(encoding='utf-8'))
        example={'portalId':'p1','pmwWorkspaceId':'w1','provider':'tandem','resourceKind':'browser_tab','providerResourceId':'tab-1','displayMode':'snapshot','interactionMode':'inspect','ownerSemanticAgentId':None,'pmwTaskId':None,'canvasObjectId':None,'metadata':{},'revision':0}
        jsonschema.validate(example,schema)
if __name__=='__main__':unittest.main()
