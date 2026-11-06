#!/usr/bin/env python3
"""Focused local regression tests for Block 8E drawing authorization hardening.

This harness imports staging_drawings_block8e.py without requiring the deployed app,
real AWS credentials, or a live database. It uses fake DB/S3 objects to verify that
project membership is enforced with object-hiding 404s across drawing and pin routes.
"""
import importlib.util
import pathlib
import sys
import types
from copy import deepcopy
from fastapi import HTTPException

ROOT = pathlib.Path(__file__).resolve().parent
MODULE_PATH = ROOT / "staging_drawings_block8e.py"

# Stub third-party/app modules required by the staging router import.
boto3 = types.ModuleType("boto3")
boto3.client = lambda *args, **kwargs: FakeS3()
botocore = types.ModuleType("botocore")
botocore_config = types.ModuleType("botocore.config")
class BotoConfig:
    def __init__(self, *args, **kwargs):
        pass
botocore_config.Config = BotoConfig
sys.modules["boto3"] = boto3
sys.modules.setdefault("botocore", botocore)
sys.modules["botocore.config"] = botocore_config
sqlalchemy = types.ModuleType("sqlalchemy")
sqlalchemy.text = lambda sql: sql
sqlalchemy_orm = types.ModuleType("sqlalchemy.orm")
class Session:
    pass
sqlalchemy_orm.Session = Session
sys.modules["sqlalchemy"] = sqlalchemy
sys.modules["sqlalchemy.orm"] = sqlalchemy_orm

app = types.ModuleType("app")
database = types.ModuleType("app.database")
auth = types.ModuleType("app.auth")
database.get_db = lambda: None
auth.get_current_user = lambda: None
auth.extract_user_info = lambda user: user
sys.modules.setdefault("app", app)
sys.modules["app.database"] = database
sys.modules["app.auth"] = auth

spec = importlib.util.spec_from_file_location("staging_drawings_block8e", MODULE_PATH)
drawings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drawings)

class MappingResult:
    def __init__(self, rows):
        self.rows = list(rows)
    def first(self):
        return self.rows[0] if self.rows else None
    def all(self):
        return self.rows

class Result:
    def __init__(self, rows=None, rowcount=0):
        self.rows = list(rows or [])
        self.rowcount = rowcount
    def first(self):
        return self.rows[0] if self.rows else None
    def mappings(self):
        return MappingResult(self.rows)

class FakeS3:
    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"signed://{operation}/{Params['Key']}?ttl={ExpiresIn}"

class FakeDB:
    def __init__(self):
        self.project_members = {1: {"owner@example.com", "member@example.com"}, 2: {"other@example.com"}}
        self.drawings = {
            10: {"id": 10, "project_id": 1, "title": "P1", "drawing_number": None, "discipline": "general", "filename": "p1.pdf", "s3_key": "drawings/projects/1/a.pdf", "file_type": "pdf", "file_size": None, "view_url": None, "thumbnail_url": None, "page_width_pts": None, "page_height_pts": None, "uploaded_by": "owner@example.com"},
            20: {"id": 20, "project_id": 2, "title": "P2", "drawing_number": None, "discipline": "general", "filename": "p2.pdf", "s3_key": "drawings/projects/2/b.pdf", "file_type": "pdf", "file_size": None, "view_url": None, "thumbnail_url": None, "page_width_pts": None, "page_height_pts": None, "uploaded_by": "other@example.com"},
        }
        self.pins = {
            100: {"id": 100, "drawing_id": 10, "finding_id": None, "tag_number": None, "label": None, "x_pct": 10, "y_pct": 20, "status": "not_started", "notes": None, "page_number": 1, "created_by": "owner@example.com"},
            200: {"id": 200, "drawing_id": 20, "finding_id": None, "tag_number": None, "label": None, "x_pct": 30, "y_pct": 40, "status": "verified", "notes": None, "page_number": 1, "created_by": "other@example.com"},
        }
        self.next_drawing_id = 30
        self.next_pin_id = 300
        self.commits = 0

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=None):
        q = str(sql).lower()
        params = params or {}
        if "from project_members" in q:
            pid = params.get("project_id")
            email = params.get("email")
            return Result([{"ok": 1}] if email in self.project_members.get(pid, set()) else [])
        if "from drawings d" in q and "join project_members" in q:
            did = params.get("drawing_id")
            email = params.get("email")
            row = self.drawings.get(did)
            if row and email in self.project_members.get(row["project_id"], set()):
                if "d.s3_key" in q and "select d.*" not in q:
                    return Result([{"s3_key": row["s3_key"]}])
                if "d.id" in q and "select d.*" not in q:
                    return Result([{"id": row["id"]}])
                return Result([deepcopy(row)])
            return Result([])
        if "from inspection_pins p" in q and "join drawings d" in q:
            pin = self.pins.get(params.get("pin_id"))
            if pin:
                dr = self.drawings.get(pin["drawing_id"])
                if dr and params.get("email") in self.project_members.get(dr["project_id"], set()):
                    return Result([{"id": pin["id"]} if "p.id" in q and "select p.*" not in q else deepcopy(pin)])
            return Result([])
        if "select * from drawings" in q and "where project_id" in q:
            pid = params.get("pid")
            disc = params.get("disc")
            rows = [deepcopy(r) for r in self.drawings.values() if r["project_id"] == pid and (disc is None or r["discipline"] == disc)]
            return Result(rows)
        if "insert into drawings" in q:
            new = dict(params)
            new["id"] = self.next_drawing_id
            self.next_drawing_id += 1
            self.drawings[new["id"]] = deepcopy(new)
            return Result([deepcopy(new)])
        if "update drawings set" in q and "returning *" in q:
            row = self.drawings.get(params.get("id"))
            if not row:
                return Result([])
            for k, v in params.items():
                if k != "id":
                    row[k] = v
            return Result([deepcopy(row)])
        if "delete from drawings" in q:
            return Result(rowcount=1 if self.drawings.pop(params.get("id"), None) else 0)
        if "returning id, page_width_pts, page_height_pts" in q:
            row = self.drawings.get(params.get("id"))
            if not row:
                return Result([])
            row["page_width_pts"] = params["page_width_pts"]
            row["page_height_pts"] = params["page_height_pts"]
            return Result([{"id": row["id"], "page_width_pts": row["page_width_pts"], "page_height_pts": row["page_height_pts"]}])
        if "select * from inspection_pins" in q:
            did = params.get("did")
            return Result([deepcopy(p) for p in self.pins.values() if p["drawing_id"] == did])
        if "insert into inspection_pins" in q:
            new = dict(params)
            new["id"] = self.next_pin_id
            self.next_pin_id += 1
            self.pins[new["id"]] = deepcopy(new)
            return Result([deepcopy(new)])
        if "delete from inspection_pins" in q:
            return Result(rowcount=1 if self.pins.pop(params.get("id"), None) else 0)
        raise AssertionError(f"Unhandled SQL: {sql}\nparams={params}")

def user(email):
    return {"email": email, "sub": email}

def assert_404(fn, detail=None):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 404, exc
        if detail:
            assert exc.detail == detail, exc.detail
    else:
        raise AssertionError("expected HTTP 404")

def test_allowed_member_paths():
    db = FakeDB()
    drawings._s3 = lambda: FakeS3()
    u = user("member@example.com")
    p = drawings.PresignRequest(project_id=1, filename="plan.pdf", content_type="application/pdf")
    presign = drawings.presign_upload(p, db, u)
    assert presign["s3_key"].startswith("drawings/projects/1/")
    assert presign["upload_url"].startswith("signed://put_object/drawings/projects/1/")
    create = drawings.DrawingCreate(project_id=1, title="New", filename="new.pdf", s3_key=presign["s3_key"], file_type="pdf")
    created = drawings.create_drawing(create, db, u)
    assert created["project_id"] == 1
    assert drawings.list_drawings(1, None, db, u)
    assert drawings.get_drawing(10, db, u)["id"] == 10
    assert drawings.get_view_url(10, db, u)["view_url"].startswith("signed://get_object/drawings/projects/1/")
    updated = drawings.update_drawing(10, drawings.DrawingUpdate(title="Updated"), db, u)
    assert updated["title"] == "Updated"
    dims = drawings.update_drawing_dimensions(10, drawings.DrawingDimensionsUpdate(page_width_pts=612, page_height_pts=792), db, u)
    assert dims["page_width_pts"] == 612
    assert drawings.list_pins(10, db, u)[0]["id"] == 100
    pin = drawings.create_pin(10, drawings.PinCreate(x_pct=1, y_pct=2, status="verified"), db, u)
    assert pin["drawing_id"] == 10 and pin["created_by"] == "member@example.com"
    drawings.delete_pin(pin["id"], db, u)
    assert pin["id"] not in db.pins
    drawings.delete_drawing(created["id"], db, u)
    assert created["id"] not in db.drawings

def test_denied_non_member_paths_object_hide():
    db = FakeDB()
    drawings._s3 = lambda: FakeS3()
    u = user("member@example.com")
    assert_404(lambda: drawings.presign_upload(drawings.PresignRequest(project_id=2, filename="x.pdf"), db, u), "Project not found")
    assert_404(lambda: drawings.list_drawings(2, None, db, u), "Project not found")
    assert_404(lambda: drawings.create_drawing(drawings.DrawingCreate(project_id=2, title="Bad", filename="bad.pdf", s3_key="drawings/projects/2/bad.pdf"), db, u), "Project not found")
    assert_404(lambda: drawings.create_drawing(drawings.DrawingCreate(project_id=1, title="Bad", filename="bad.pdf", s3_key="drawings/projects/2/bad.pdf"), db, u), "Drawing not found")
    assert_404(lambda: drawings.get_drawing(20, db, u), "Drawing not found")
    assert_404(lambda: drawings.get_view_url(20, db, u), "Drawing not found")
    assert_404(lambda: drawings.update_drawing(20, drawings.DrawingUpdate(title="Nope"), db, u), "Drawing not found")
    assert_404(lambda: drawings.update_drawing_dimensions(20, drawings.DrawingDimensionsUpdate(page_width_pts=1, page_height_pts=1), db, u), "Drawing not found")
    assert_404(lambda: drawings.list_pins(20, db, u), "Drawing not found")
    assert_404(lambda: drawings.create_pin(20, drawings.PinCreate(x_pct=1, y_pct=2), db, u), "Drawing not found")
    assert_404(lambda: drawings.delete_pin(200, db, u), "Pin not found")
    assert_404(lambda: drawings.delete_drawing(20, db, u), "Drawing not found")
    assert 20 in db.drawings and 200 in db.pins

if __name__ == "__main__":
    test_allowed_member_paths()
    test_denied_non_member_paths_object_hide()
    print("OK: drawing authorization regression tests passed")
