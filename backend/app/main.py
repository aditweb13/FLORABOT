from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx
from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from . import models
from .config import settings
from .database import Base, engine, get_db
from .services import analyze_plant, chat_reply, generate_report, save_image, ensure_dirs

Base.metadata.create_all(bind=engine); ensure_dirs()
app = FastAPI(title="FloraBot API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def image_url(path): return "/files/" + Path(path).name if path else None
def severity_value(value):
    value=(value or "").strip()
    return "" if not value or any(marker in value.lower() for marker in ("not provided","unavailable","unknown")) else value
def analysis_out(a):
    return {"id":a.id,"plant_id":a.plant_id,"image":image_url(a.image),"timestamp":a.timestamp,"plant_identification":a.plant_identification,"disease_detected":a.disease_detected,"disease_name":a.disease_name,"severity":severity_value(a.severity),"health_status":a.health_status,"confidence":a.confidence,"symptoms":a.symptoms,"recommendations":a.recommendations,"prevention":a.prevention}
def plant_out(p, detail=False):
    latest = max(p.analyses, key=lambda a:a.timestamp) if p.analyses else None
    data = {"id":p.id,"name":p.name,"species":p.species,"category":p.category,"image":image_url(p.image),"registered_at":p.registered_at,"location":p.location,"notes":p.notes,"health_status":p.health_status,"scan_count":len(p.analyses),"last_scan":latest.timestamp if latest else None,"latest_analysis":analysis_out(latest) if latest else None}
    if detail: data["analyses"] = [analysis_out(a) for a in sorted(p.analyses,key=lambda x:x.timestamp,reverse=True)]; data["reports"] = [{"id":r.id,"created_at":r.created_at,"download_url":f"/api/reports/{r.id}/download"} for r in p.reports]
    return data

@app.get("/api/health")
def health(): return {"status":"ok","diagnosis_configured":bool(settings.plant_id_api_key),"chat_configured":bool(settings.groq_api_key)}

@app.get("/files/{filename}")
def get_file(filename:str):
    for root in (settings.upload_dir, settings.report_dir):
        path=Path(root)/Path(filename).name
        if path.is_file(): return FileResponse(path)
    raise HTTPException(404,"File not found")

@app.get("/api/plants")
def list_plants(db:Session=Depends(get_db)): return [plant_out(p) for p in db.query(models.Plant).order_by(models.Plant.registered_at.desc()).all()]

@app.post("/api/plants")
async def create_plant(name:str=Form(...), species:str=Form("Unknown"), category:str=Form("Other"), location:str=Form(""), notes:str=Form(""), image:Optional[UploadFile]=File(None), db:Session=Depends(get_db)):
    img=None
    if image:
        try: img=save_image(await image.read(),image.filename or "plant.jpg")
        except ValueError as e: raise HTTPException(400,str(e))
    p=models.Plant(name=name.strip(),species=species.strip() or "Unknown",category=category,location=location,notes=notes,image=img); db.add(p); db.commit(); db.refresh(p); return plant_out(p)

@app.get("/api/plants/{plant_id}")
def get_plant(plant_id:int,db:Session=Depends(get_db)):
    p=db.get(models.Plant,plant_id)
    if not p: raise HTTPException(404,"Plant not found")
    return plant_out(p,True)

@app.delete("/api/plants/{plant_id}")
def delete_plant(plant_id:int,db:Session=Depends(get_db)):
    p=db.get(models.Plant,plant_id)
    if not p: raise HTTPException(404,"Plant not found")
    image_paths=[x for x in [p.image,*(a.image for a in p.analyses)] if x]
    report_paths=[r.file_path for r in p.reports if r.file_path]
    p_name=p.name
    try:
        for convo in db.query(models.Conversation).filter(models.Conversation.plant_id==p.id).all():
            db.delete(convo)
        db.delete(p)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500,"Could not delete this plant or its associated records. Please try again.") from exc
    for value,root in [(x,settings.upload_dir) for x in image_paths]+[(x,settings.report_dir) for x in report_paths]:
        try:
            path=Path(value).resolve()
            if path.is_relative_to(Path(root).resolve()) and path.is_file():path.unlink()
        except (OSError,ValueError):
            pass
    return {"ok":True,"deleted_plant_id":plant_id,"name":p_name,"message":"Plant and its associated records were deleted."}

@app.patch("/api/plants/{plant_id}")
async def update_plant(plant_id:int,name:Optional[str]=Form(None),species:Optional[str]=Form(None),category:Optional[str]=Form(None),location:Optional[str]=Form(None),notes:Optional[str]=Form(None),image:Optional[UploadFile]=File(None),db:Session=Depends(get_db)):
    p=db.get(models.Plant,plant_id)
    if not p: raise HTTPException(404,"Plant not found")
    for k,v in {"name":name,"species":species,"category":category,"location":location,"notes":notes}.items():
        if v is not None: setattr(p,k,v)
    if image:
        try:p.image=save_image(await image.read(),image.filename or "plant.jpg")
        except ValueError as e: raise HTTPException(400,str(e))
    db.commit();db.refresh(p);return plant_out(p)

@app.post("/api/plants/{plant_id}/analyze")
async def analyze(plant_id:int,image:UploadFile=File(...),db:Session=Depends(get_db)):
    p=db.get(models.Plant,plant_id)
    if not p: raise HTTPException(404,"Plant not found")
    try: path=save_image(await image.read(),image.filename or "leaf.jpg")
    except ValueError as e: raise HTTPException(400,str(e))
    try: result=analyze_plant(path)
    except RuntimeError as e: raise HTTPException(503,str(e))
    except httpx.HTTPStatusError as e: raise HTTPException(502,"Plant diagnosis provider returned an error. Check settings and try again.")
    except Exception: raise HTTPException(502,"Could not complete plant diagnosis. Please try again.")
    a=models.Analysis(plant_id=p.id,image=path,plant_identification=result["plant_identification"],disease_detected=result["disease_detected"],disease_name=result["disease_name"],severity=result["severity"],health_status=result["health_status"],confidence=result["confidence"],symptoms=result["symptoms"],recommendations=result["recommendations"],prevention=result["prevention"],provider_reference=result["provider_reference"])
    db.add(a);p.health_status=a.health_status
    if p.species in ("Unknown", ""): p.species=a.plant_identification
    db.commit();db.refresh(a);return analysis_out(a)

@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id:int,db:Session=Depends(get_db)):
    a=db.get(models.Analysis,analysis_id)
    if not a:raise HTTPException(404,"Analysis not found")
    return analysis_out(a)

class ChatIn(BaseModel): message:str; conversation_id:Optional[int]=None; plant_id:Optional[int]=None
@app.post("/api/chat")
def chat(body:ChatIn,db:Session=Depends(get_db)):
    convo=db.get(models.Conversation,body.conversation_id) if body.conversation_id else None
    if not convo: convo=models.Conversation(plant_id=body.plant_id);db.add(convo);db.commit();db.refresh(convo)
    if body.plant_id: convo.plant_id=body.plant_id
    context=""
    if convo.plant_id:
        p=db.get(models.Plant,convo.plant_id)
        if p:
            latest=max(p.analyses,key=lambda a:a.timestamp) if p.analyses else None
            context=f"Plant context: {p.name}, species {p.species}, current status {p.health_status}. Latest scan: {latest.disease_name or latest.health_status}; findings: {latest.symptoms}" if latest else f"Plant context: {p.name}, species {p.species}; no scans yet."
    msgs=[{"role":m.role,"content":m.content} for m in sorted(convo.messages,key=lambda m:m.created_at)]
    user=models.ChatMessage(conversation_id=convo.id,role="user",content=body.message);db.add(user);db.commit()
    try: answer=chat_reply(msgs+[{"role":"user","content":body.message}],context)
    except RuntimeError as e: raise HTTPException(503,str(e))
    except httpx.HTTPStatusError: raise HTTPException(502,"FloraBot could not reach the chat provider. Please try again.")
    except Exception: raise HTTPException(502,"FloraBot chat is temporarily unavailable.")
    assistant=models.ChatMessage(conversation_id=convo.id,role="assistant",content=answer);db.add(assistant);db.commit()
    return {"conversation_id":convo.id,"reply":answer,"messages":[{"role":m.role,"content":m.content,"created_at":m.created_at} for m in sorted(convo.messages,key=lambda m:m.created_at)]}

@app.delete("/api/conversations/{conversation_id}")
def clear_chat(conversation_id:int,db:Session=Depends(get_db)):
    convo=db.get(models.Conversation,conversation_id)
    if convo:db.delete(convo);db.commit()
    return {"ok":True}

@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id:int,db:Session=Depends(get_db)):
    convo=db.get(models.Conversation,conversation_id)
    if not convo:raise HTTPException(404,"Conversation not found")
    return {"conversation_id":convo.id,"plant_id":convo.plant_id,"messages":[{"role":m.role,"content":m.content,"created_at":m.created_at} for m in sorted(convo.messages,key=lambda m:m.created_at)]}

@app.get("/api/dashboard")
def dashboard(db:Session=Depends(get_db)):
    plants=db.query(models.Plant).all(); analyses=db.query(models.Analysis).order_by(models.Analysis.timestamp.desc()).limit(8).all()
    return {"total":len(plants),"healthy":sum(p.health_status=="Healthy" for p in plants),"attention":sum(p.health_status=="Needs Attention" for p in plants),"diseased":sum(p.health_status=="Disease Detected" for p in plants),"unscanned":sum(p.health_status=="Unscanned" for p in plants),"plants":[plant_out(p) for p in plants],"recent_analyses":[{**analysis_out(a),"plant_name":a.plant.name} for a in analyses]}

@app.post("/api/plants/{plant_id}/reports")
def create_report(plant_id:int,analysis_id:Optional[int]=None,db:Session=Depends(get_db)):
    p=db.get(models.Plant,plant_id)
    if not p:raise HTTPException(404,"Plant not found")
    a=db.get(models.Analysis,analysis_id) if analysis_id else (max(p.analyses,key=lambda x:x.timestamp) if p.analyses else None)
    if not a or a.plant_id!=p.id:raise HTTPException(400,"Run a scan before creating a report.")
    output=str(Path(settings.report_dir)/f"flora-report-{p.id}-{a.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
    try:generate_report(p,a,output)
    except Exception:raise HTTPException(500,"Could not generate the PDF report.")
    r=models.Report(plant_id=p.id,analysis_id=a.id,file_path=output);db.add(r);db.commit();db.refresh(r)
    return {"id":r.id,"download_url":f"/api/reports/{r.id}/download"}

@app.get("/api/reports/{report_id}/download")
def download_report(report_id:int,db:Session=Depends(get_db)):
    r=db.get(models.Report,report_id)
    if not r or not Path(r.file_path).is_file():raise HTTPException(404,"Report not found")
    return FileResponse(r.file_path,media_type="application/pdf",filename=Path(r.file_path).name)

@app.get("/api/settings")
def get_settings():return {"camera_stream_url":settings.camera_stream_url,"camera_snapshot_url":settings.camera_snapshot_url,"diagnosis_configured":bool(settings.plant_id_api_key),"chat_configured":bool(settings.groq_api_key),"chat_model":settings.groq_model}

@app.post("/api/settings/test-camera")
def test_camera(url:str):
    try:
        with httpx.Client(timeout=5) as client:r=client.get(url)
        return {"connected":r.status_code<400,"status_code":r.status_code}
    except Exception:return {"connected":False,"message":"Camera endpoint did not respond. Check the address and local network."}

@app.get("/api/camera/snapshot")
def camera_snapshot(url:str):
    try:
        with httpx.Client(timeout=8,follow_redirects=True) as client:r=client.get(url)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):raise HTTPException(415,"Camera snapshot endpoint did not return an image.")
        from fastapi.responses import Response
        return Response(content=r.content,media_type=r.headers["content-type"],headers={"Cache-Control":"no-store"})
    except HTTPException:raise
    except Exception:raise HTTPException(502,"Camera snapshot is unavailable. Check the URL and local network.")

@app.post("/api/settings/test-ai")
def test_ai():return {"diagnosis_configured":bool(settings.plant_id_api_key),"chat_configured":bool(settings.groq_api_key)}
