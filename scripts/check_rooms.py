"""Verify all curated room proofs without credentials, rendering, or providers."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from parallax_relay.room_certificates import verify_catalog
from parallax_relay.rooms import catalog_identity

if __name__=='__main__':
    print(json.dumps({'schema_version':1,'catalog_sha256':catalog_identity()['sha256'],'rooms':verify_catalog()},indent=2))
