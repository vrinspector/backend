# app/routers/drawings.py  —  Block 8E adapted from staging Block 8D v3
# Matches frontend API call patterns exactly:
#   POST /v1/drawings/presign      (frontend sends POST with JSON body)
#   GET  /v1/drawings?project_id=N (frontend uses query param, not path param)
import boto3, os, uuid
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user, extract_user_info

router = APIRouter(prefix="/v1")

S3_BUCKET  = os.getenv("S3_BUCKET",  "vrinspector-files")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def _s3():
    return boto3.client("s3", region_name=AWS_REGION,
                        config=BotoConfig(signature_version="s3v4"))


def _dump_model(model):
    """Pydantic v1/v2 compatibility for the staging patch artifact."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _current_user_email(current_user):
    user_info = extract_user_info(current_user)
    return user_info.get("email") or user_info.get("sub") or "inspector"


def _not_found(detail="Drawing not found"):
    # Object-hiding response: use 404 for missing and unauthorized objects.
    raise HTTPException(status_code=404, detail=detail)


def _project_s3_prefix(project_id: int) -> str:
    return f"drawings/projects/{int(project_id)}/"


def _safe_extension(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext in {".pdf", ".png", ".jpg", ".jpeg", ".svg"} else ""


def _validate_project_s3_key(project_id: int, s3_key: str):
    prefix = _project_s3_prefix(project_id)
    if not s3_key or not str(s3_key).startswith(prefix):
        _not_found("Drawing not found")


def _require_project_member(db: Session, project_id: int, current_user):
    user_email = _current_user_email(current_user)
    row = db.execute(text("""
        SELECT 1
        FROM project_members
        WHERE project_id = :project_id AND user_email = :email
        LIMIT 1
    """), {"project_id": project_id, "email": user_email}).first()
    if not row:
        _not_found("Project not found")
    return user_email


def _get_authorized_drawing(db: Session, drawing_id: int, current_user, columns: str = "d.*"):
    user_email = _current_user_email(current_user)
    row = db.execute(text(f"""
        SELECT {columns}
        FROM drawings d
        JOIN project_members pm ON pm.project_id = d.project_id
        WHERE d.id = :drawing_id AND pm.user_email = :email
        LIMIT 1
    """), {"drawing_id": drawing_id, "email": user_email}).mappings().first()
    if not row:
        _not_found("Drawing not found")
    return row


def _get_authorized_pin(db: Session, pin_id: int, current_user, columns: str = "p.*"):
    user_email = _current_user_email(current_user)
    row = db.execute(text(f"""
        SELECT {columns}
        FROM inspection_pins p
        JOIN drawings d ON d.id = p.drawing_id
        JOIN project_members pm ON pm.project_id = d.project_id
        WHERE p.id = :pin_id AND pm.user_email = :email
        LIMIT 1
    """), {"pin_id": pin_id, "email": user_email}).mappings().first()
    if not row:
        _not_found("Pin not found")
    return row


# ── Schemas ───────────────────────────────────────────────────

class PresignRequest(BaseModel):
    project_id:    int
    filename:      str
    content_type:  str = "application/octet-stream"

class DrawingCreate(BaseModel):
    project_id:     int
    title:          str
    drawing_number: Optional[str] = None
    discipline:     str = "general"
    filename:       str
    s3_key:         str
    file_type:      str = "png"
    file_size:      Optional[int] = None
    view_url:       Optional[str] = None
    thumbnail_url:  Optional[str] = None
    page_width_pts: Optional[float] = None
    page_height_pts: Optional[float] = None

class DrawingUpdate(BaseModel):
    title:          Optional[str] = None
    drawing_number: Optional[str] = None
    discipline:     Optional[str] = None
    view_url:       Optional[str] = None
    thumbnail_url:  Optional[str] = None

class DrawingDimensionsUpdate(BaseModel):
    page_width_pts: float
    page_height_pts: float

class PinCreate(BaseModel):
    finding_id:  Optional[int] = None
    tag_number:  Optional[str] = None
    label:       Optional[str] = None
    x_pct:       float
    y_pct:       float
    status:      str = "not_started"
    notes:       Optional[str] = None
    page_number: int = 1

class PinUpdate(BaseModel):
    finding_id:  Optional[int] = None
    tag_number:  Optional[str] = None
    label:       Optional[str] = None
    status:      Optional[str] = None
    notes:       Optional[str] = None


# ── Drawing endpoints ─────────────────────────────────────────

# Frontend calls: POST /v1/drawings/presign  with JSON {project_id, filename, content_type}
@router.post("/drawings/presign")
def presign_upload(
    payload: PresignRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_project_member(db, payload.project_id, current_user)
    ext = _safe_extension(payload.filename)
    key = f"{_project_s3_prefix(payload.project_id)}{uuid.uuid4().hex}{ext}"
    url = _s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": S3_BUCKET, "Key": key, "ContentType": payload.content_type},
        ExpiresIn=600,
    )
    return {"upload_url": url, "s3_key": key}


@router.post("/drawings", status_code=201)
def create_drawing(
    payload: DrawingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    uploaded_by = _require_project_member(db, payload.project_id, current_user)
    _validate_project_s3_key(payload.project_id, payload.s3_key)
    row = db.execute(text("""
        INSERT INTO drawings
            (project_id, title, drawing_number, discipline, filename,
             s3_key, file_type, file_size, view_url, thumbnail_url,
             page_width_pts, page_height_pts, uploaded_by)
        VALUES
            (:project_id, :title, :drawing_number, :discipline, :filename,
             :s3_key, :file_type, :file_size, :view_url, :thumbnail_url,
             :page_width_pts, :page_height_pts, :uploaded_by)
        RETURNING *
    """), {**_dump_model(payload), "uploaded_by": uploaded_by}).mappings().first()
    db.commit()
    return dict(row)


# Frontend calls: GET /v1/drawings?project_id=N
@router.get("/drawings")
def list_drawings(
    project_id: int = Query(...),
    discipline: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_project_member(db, project_id, current_user)
    if discipline:
        rows = db.execute(text("""
            SELECT * FROM drawings
            WHERE project_id = :pid AND discipline = :disc
            ORDER BY created_at DESC
        """), {"pid": project_id, "disc": discipline}).mappings().all()
    else:
        rows = db.execute(text("""
            SELECT * FROM drawings
            WHERE project_id = :pid
            ORDER BY created_at DESC
        """), {"pid": project_id}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/drawings/{drawing_id}")
def get_drawing(
    drawing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    row = _get_authorized_drawing(db, drawing_id, current_user)
    return dict(row)


@router.put("/drawings/{drawing_id}")
def update_drawing(
    drawing_id: int,
    payload: DrawingUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_authorized_drawing(db, drawing_id, current_user, "d.id")
    updates = {k: v for k, v in _dump_model(payload).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = drawing_id
    row = db.execute(text(f"""
        UPDATE drawings SET {set_clause}, updated_at = NOW()
        WHERE id = :id RETURNING *
    """), updates).mappings().first()
    if not row:
        _not_found("Drawing not found")
    db.commit()
    return dict(row)


@router.delete("/drawings/{drawing_id}", status_code=204)
def delete_drawing(
    drawing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_authorized_drawing(db, drawing_id, current_user, "d.id")
    result = db.execute(text("DELETE FROM drawings WHERE id = :id"), {"id": drawing_id})
    db.commit()
    if result.rowcount == 0:
        _not_found("Drawing not found")


@router.patch("/drawings/{drawing_id}/dimensions")
def update_drawing_dimensions(
    drawing_id: int,
    payload: DrawingDimensionsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Store captured PDF MediaBox dimensions for future coordinate migration."""
    _get_authorized_drawing(db, drawing_id, current_user, "d.id")
    row = db.execute(text("""
        UPDATE drawings
        SET page_width_pts = :page_width_pts,
            page_height_pts = :page_height_pts,
            updated_at = NOW()
        WHERE id = :id
        RETURNING id, page_width_pts, page_height_pts
    """), {
        "id": drawing_id,
        "page_width_pts": payload.page_width_pts,
        "page_height_pts": payload.page_height_pts,
    }).mappings().first()
    if not row:
        _not_found("Drawing not found")
    db.commit()
    return dict(row)


# ── Pin endpoints ─────────────────────────────────────────────

@router.get("/drawings/{drawing_id}/pins")
def list_pins(
    drawing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_authorized_drawing(db, drawing_id, current_user, "d.id")
    rows = db.execute(text("""
        SELECT * FROM inspection_pins WHERE drawing_id = :did ORDER BY id
    """), {"did": drawing_id}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/drawings/{drawing_id}/pins", status_code=201)
def create_pin(
    drawing_id: int,
    payload: PinCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    created_by = _current_user_email(current_user)
    _get_authorized_drawing(db, drawing_id, current_user, "d.id")
    row = db.execute(text("""
        INSERT INTO inspection_pins
            (drawing_id, finding_id, tag_number, label,
             x_pct, y_pct, status, notes, page_number, created_by)
        VALUES
            (:drawing_id, :finding_id, :tag_number, :label,
             :x_pct, :y_pct, :status, :notes, :page_number, :created_by)
        RETURNING *
    """), {**_dump_model(payload), "drawing_id": drawing_id, "created_by": created_by}).mappings().first()
    db.commit()
    return dict(row)


@router.delete("/pins/{pin_id}", status_code=204)
def delete_pin(
    pin_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_authorized_pin(db, pin_id, current_user, "p.id")
    result = db.execute(text("DELETE FROM inspection_pins WHERE id = :id"), {"id": pin_id})
    db.commit()
    if result.rowcount == 0:
        _not_found("Pin not found")


# ── View-URL — presigned GET URL for rendering in browser
@router.get("/drawings/{drawing_id}/view-url")
def get_view_url(
    drawing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    row = _get_authorized_drawing(db, drawing_id, current_user, "d.s3_key")
    url = _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": row["s3_key"]},
        ExpiresIn=3600,
    )
    return {"view_url": url}
