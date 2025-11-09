import os
import hashlib
import io
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from bson import ObjectId
from database import db
from datetime import datetime, timezone

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility helpers

def oid(obj_id: str) -> ObjectId:
    try:
        return ObjectId(obj_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def make_slug() -> str:
    return hashlib.sha1(os.urandom(16)).hexdigest()[:8]


# Schemas for request bodies

class ExamCreate(BaseModel):
    url: HttpUrl
    password: str


class VerifyBody(BaseModel):
    password: str


class LogBody(BaseModel):
    type: str
    details: Optional[str] = ""
    ts: Optional[int] = None


@app.get("/")
def read_root():
    return {"message": "ProctorLink API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
    }
    try:
        if db is not None:
            _ = db.list_collection_names()
            response["database"] = "✅ Connected"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:60]}"
    return response


@app.post("/exams")
async def create_exam(body: ExamCreate, request: Request):
    if db is None:
        raise HTTPException(500, "Database not configured")

    slug = make_slug()
    password_hash = hash_password(body.password)
    exam_doc = {
        "url": str(body.url),
        "password_hash": password_hash,
        "slug": slug,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    exam_id = db["exam"].insert_one(exam_doc).inserted_id

    frontend_base = os.getenv("FRONTEND_BASE_URL")
    path = f"/x/{slug}"
    if frontend_base:
        short_url = f"{frontend_base.rstrip('/')}{path}"
    else:
        base = str(request.base_url).rstrip('/')
        short_url = f"{base}{path}"

    return {
        "id": str(exam_id),
        "slug": slug,
        "short_url": short_url,
        "embed_url": str(body.url),
    }


@app.get("/exams/slug/{slug}")
async def get_exam_by_slug(slug: str):
    if db is None:
        raise HTTPException(500, "Database not configured")
    doc = db["exam"].find_one({"slug": slug})
    if not doc:
        raise HTTPException(404, "Exam not found")
    return {"id": str(doc["_id"]), "slug": slug, "embed_url": doc["url"]}


@app.post("/exams/{exam_id}/verify")
async def verify_exam_password(exam_id: str, body: VerifyBody):
    if db is None:
        raise HTTPException(500, "Database not configured")
    doc = db["exam"].find_one({"_id": oid(exam_id)})
    if not doc:
        raise HTTPException(404, "Exam not found")
    ok = doc.get("password_hash") == hash_password(body.password)
    return {"ok": ok, "message": "OK" if ok else "Invalid password"}


@app.post("/exams/{exam_id}/log")
async def log_event(exam_id: str, body: LogBody, request: Request):
    if db is None:
        raise HTTPException(500, "Database not configured")
    if not db["exam"].find_one({"_id": oid(exam_id)}):
        raise HTTPException(404, "Exam not found")
    evt = {
        "exam_id": oid(exam_id),
        "type": body.type,
        "details": body.details or "",
        "client_ts": body.ts,
        "server_ts": datetime.now(timezone.utc),
        "ip": request.client.host if request.client else None,
        "ua": request.headers.get("user-agent"),
    }
    db["examlog"].insert_one(evt)
    return {"ok": True}


@app.get("/exams/{exam_id}/export")
async def export_log(exam_id: str):
    if db is None:
        raise HTTPException(500, "Database not configured")
    if not db["exam"].find_one({"_id": oid(exam_id)}):
        raise HTTPException(404, "Exam not found")

    logs = list(db["examlog"].find({"exam_id": oid(exam_id)}).sort("server_ts", 1))

    try:
        from openpyxl import Workbook
    except Exception:
        raise HTTPException(500, "openpyxl not installed on server")

    wb = Workbook()
    ws = wb.active
    ws.title = "Proctor Log"
    ws.append(["#", "Event", "Details", "Client Time", "Server Time", "IP", "User Agent"]) 

    for i, l in enumerate(logs, start=1):
        client_time = (
            datetime.fromtimestamp(l.get("client_ts") / 1000.0).isoformat()
            if l.get("client_ts") else ""
        )
        server_time = l.get("server_ts").astimezone(timezone.utc).isoformat() if l.get("server_ts") else ""
        ws.append([
            i,
            l.get("type"),
            l.get("details"),
            client_time,
            server_time,
            l.get("ip"),
            l.get("ua"),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"exam_{exam_id}_log.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return StreamingResponse(buf, headers=headers)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
