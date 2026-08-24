from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Any
from ..errors import ProviderUnavailableError

class HerdrBridgeImportAdapter:
    """Read-only importer from the existing eml_bridge journal. No runtime side effect."""
    def __init__(self,path:str|Path): self.path=Path(path)

    def read_agent(self,semantic_agent_id:str)->dict[str,Any]:
        if not self.path.exists(): raise ProviderUnavailableError(f'bridge db not found: {self.path}')
        conn=sqlite3.connect(self.path); conn.row_factory=sqlite3.Row
        try:
            row=conn.execute('SELECT display_name,role,binding_json FROM agents WHERE semantic_agent_id=?',(semantic_agent_id,)).fetchone()
        except sqlite3.OperationalError as exc:
            raise ProviderUnavailableError('bridge agents table not available') from exc
        finally:
            pass
        if not row:
            conn.close(); raise KeyError(semantic_agent_id)
        out={'semantic_agent_id':semantic_agent_id,'display_name':row['display_name'],'role':row['role'],'runtime_binding':json.loads(row['binding_json'])}
        conn.close(); return out
