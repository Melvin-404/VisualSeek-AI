import os
import re
import uuid
import json
import logging
import datetime
import tempfile
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, File, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet
import structlog
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.security import TokenPayload, hash_api_key
from app.core.rbac.roles import RoleEnum
from app.db.session import get_db
from app.models.schema_models import Camera, CameraAssignment
from app.services.nl_query.parser import NLUQueryParser
from app.services.vector_search import VectorSearchService
from app.core.auth.keycloak import get_redis_client

logger = structlog.get_logger("api.chat")
router = APIRouter(prefix="/chat", tags=["Conversational AI Search"])

nlu_parser = NLUQueryParser()
vector_search_service = VectorSearchService()

# Encryption setup for history at rest
fernet = Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_history(history_list: List[Dict[str, Any]]) -> bytes:
    data_str = json.dumps(history_list)
    return fernet.encrypt(data_str.encode())

def decrypt_history(encrypted_data: bytes) -> List[Dict[str, Any]]:
    decrypted_bytes = fernet.decrypt(encrypted_data)
    return json.loads(decrypted_bytes.decode())

# Prompt injection detection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"ignore\s+above\s+instructions",
    r"system\s+prompt",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"bypass\s+restrictions",
    r"dan\s+mode",
    r"jailbreak",
    r"as\s+an\s+ai\s+without\s+restrictions",
    r"you\s+must\s+now\s+act\s+as",
]

def is_prompt_injection(text: str) -> bool:
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

# Rate limiting helper (100 queries/hour per user)
async def check_rate_limit(user_id: str, redis_client) -> bool:
    if not redis_client:
        return True
    key = f"chat_rate_limit:{user_id}"
    try:
        current = await redis_client.get(key)
        if current and int(current) >= 100:
            return False
        
        async with redis_client.pipeline() as pipe:
            await pipe.incr(key)
            if not current:
                await pipe.expire(key, 3600)  # 1 hour
            await pipe.execute()
    except Exception as e:
        logger.warning("Redis rate limit check failed, bypassing", error=str(e))
        return True
    return True

# Audit logging helper
def audit_log_chat(user_id: str, tenant_id: str, query: str, response: str):
    log_record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "query": query,
        "response": response
    }
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    audit_file = os.path.join(log_dir, "chat_audit.jsonl")
    try:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_record) + "\n")
    except Exception as e:
        logger.error("Failed to write chat compliance audit log", error=str(e))

# Allowed camera resolution logic for multi-tenancy
async def get_allowed_camera_ids(tenant_id: str, role: str, sub: str, db: AsyncSession) -> List[str]:
    allowed_ids = []
    if tenant_id:
        try:
            tenant_uuid = uuid.UUID(tenant_id)
            camera_stmt = select(Camera).where(Camera.org_id == tenant_uuid)
            camera_res = await db.execute(camera_stmt)
            cameras = camera_res.scalars().all()
            
            if role == RoleEnum.OPERATOR:
                user_uuid = uuid.UUID(sub)
                assign_stmt = select(CameraAssignment.camera_id).where(
                    CameraAssignment.user_id == user_uuid
                )
                assign_res = await db.execute(assign_stmt)
                assigned_ids = {str(cid) for cid in assign_res.scalars().all()}
                allowed_ids = [str(c.id) for c in cameras if str(c.id) in assigned_ids]
            else:
                allowed_ids = [str(c.id) for c in cameras]
        except ValueError:
            pass
    return allowed_ids

# Token validation function for WebSocket query parameters
async def authenticate_ws(token: Optional[str], db: AsyncSession) -> Optional[TokenPayload]:
    if not token:
        return None
        
    if token == "mock-token":
        # Static mock payload for testing / development without Keycloak
        return TokenPayload(
            sub="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
            role="viewer",
            roles=["viewer"],
            scopes=["query:execute"],
            exp=float("inf")
        )
        
    try:
        from app.core.auth.jwt import decode_and_verify_token
        from app.core.auth.keycloak import is_token_blacklisted
        
        payload = decode_and_verify_token(token)
        if await is_token_blacklisted(payload):
            return None
            
        tenant_id = payload.get("tenant_id") or payload.get("org_id")
        if not tenant_id:
            from app.models.schema_models import User
            try:
                user_uuid = uuid.UUID(payload.get("sub"))
                user_stmt = select(User).where(User.id == user_uuid)
                user_res = await db.execute(user_stmt)
                db_user = user_res.scalars().first()
                if db_user:
                    tenant_id = str(db_user.org_id)
            except Exception:
                pass
                
        if not tenant_id:
            tenant_id = "00000000-0000-0000-0000-000000000000"
            
        roles = []
        if "realm_access" in payload and isinstance(payload["realm_access"], dict):
            roles = payload["realm_access"].get("roles", [])
        elif "role" in payload:
            roles = [payload["role"]]
            
        valid_roles = [r for r in roles if r in RoleEnum.__members__.values()]
        role = valid_roles[0] if valid_roles else "viewer"
        
        return TokenPayload(
            sub=str(payload.get("sub")),
            tenant_id=str(tenant_id),
            role=role,
            roles=roles,
            scopes=payload.get("scope", "").split(" ") if "scope" in payload else [],
            exp=float(payload.get("exp", 0))
        )
    except Exception as e:
        logger.warning("WebSocket JWT Auth failed", error=str(e))
        return None

# Voice audio transcription POST endpoint
@router.post("/transcribe", response_model=Dict[str, str])
async def transcribe_audio(
    file: UploadFile = File(...),
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Transcribes uploaded voice search audio using Whisper API, falling back to mock in offline mode."""
    # Authenticate via header token or parameter token
    user_payload = await authenticate_ws(token, db)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed."
        )

    # If OpenAI API Key is missing, return a smart mock transcription based on audio length/contents
    if not settings.OPENAI_API_KEY:
        await asyncio.sleep(0.5) # Simulate latency
        # deterministic transcriptions depending on filename/size
        content = file.filename.lower() if file.filename else ""
        if "lobby" in content:
            return {"text": "person carrying backpack in lobby"}
        elif "parking" in content:
            return {"text": "white SUV in parking lot"}
        elif "roadway" in content or "traffic" in content:
            return {"text": "blue motorcycle on roadway"}
        else:
            return {"text": "people in the front lobby entrance"}

    # Write file to temporary space
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return {"text": transcript.text}
    except Exception as e:
        logger.error("Whisper transcription failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

# Query Refinement System Prompt
REFINEMENT_SYSTEM_PROMPT = """Given the conversation history and a follow-up user search query, rewrite it into a single search query that incorporates the context.
Output ONLY the refined, standalone search query. Do not add any conversational responses, reasoning, or markdown formatting.

Example 1:
History:
User: white cars in parking lot
Assistant: Found 3 white cars.
User: now only white SUVs
Refined standsalone query: white SUV in parking lot

Example 2:
History:
User: people wearing jackets
Assistant: Found 2 people wearing jackets.
User: show only lobby camera
Refined standsalone query: people wearing jackets in lobby"""

# Assistant System Prompt
CHAT_SYSTEM_PROMPT = """You are VisionQuery AI, an expert video surveillance analytics conversational assistant.
Your goal is to help operators search across video feeds, summarize search results, and explain matches.

You are given:
1. The user's query and their multi-turn conversation history.
2. The search results retrieved from the vector database.

Provide a response containing:
1. A summary of the search results (e.g. "Found 3 matching events: 2 in lobby, 1 in parking lot").
2. An explanation of why each search result matched the query based on its description and attributes.
3. Suggest 3 short, relevant follow-up queries (e.g., "Show only the ones in parking lot B", "Search for people near them").

Format your suggestions at the very end of your response, starting with the marker '[SUGGESTIONS]' followed by each suggestion on a new line, like this:
[SUGGESTIONS]
Show only the ones in parking lot B
Search for people near them
What happened at the loading dock?

Be precise, professional, and clear. Do not refer to internal technical ids (like mock-lobby-1) unless helpful; use camera friendly names.
"""

async def query_llm_refinement(query: str, history: List[Dict[str, Any]]) -> str:
    """Uses LLM to merge conversation history with the new message into a Standalone Search Query."""
    if not settings.OPENAI_API_KEY and not settings.ANTHROPIC_API_KEY:
        # Client side heuristic in mock mode
        if "only" in query.lower() or "show" in query.lower() or "just" in query.lower():
            # Try to concatenate with last query
            last_user_query = ""
            for turn in reversed(history):
                if turn.get("role") == "user":
                    last_user_query = turn.get("content", "")
                    break
            return f"{last_user_query} {query}".strip()
        return query

    history_str = "\n".join([f"{h['role'].capitalize()}: {h['content']}" for h in history])
    
    try:
        if settings.LLM_PROVIDER == "openai":
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            res = await client.chat.completions.create(
                model=settings.LLM_MODEL_OPENAI,
                messages=[
                    {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"History:\n{history_str}\n\nUser follow-up: {query}\nRefined standalone query:"}
                ],
                max_tokens=50,
                temperature=0.0
            )
            return res.choices[0].message.content.strip()
        # Fallback to simple
        return query
    except Exception as e:
        logger.warning("LLM refinement failed, using raw query", error=str(e))
        return query

async def fetch_llm_stream(query: str, history: List[Dict[str, Any]], results: List[Dict[str, Any]]):
    """Streams chat completions sentence by sentence using OpenAI/Anthropic or Mock generator."""
    if not settings.OPENAI_API_KEY and not settings.ANTHROPIC_API_KEY:
        # Mock streaming simulation
        summary = f"I scanned the surveillance feeds. Found {len(results)} matching frames."
        if results:
            summary += " Here is why they match:\n\n"
            for i, r in enumerate(results):
                summary += f"Frame Match #{i+1} on camera '{CAMERA_NAMES.get(r['camera_id'], r['camera_id'])}' matches because the system detected {', '.join(r['object_classes'])} with a score of {(r['score']*100):.0f}%. Description: \"{r['raw_labels']['description']}\".\n"
        else:
            summary += " No matching detections were located in the active camera grids."
            
        summary += "\n[SUGGESTIONS]\nShow only the ones in parking lot B\nSearch for people near them\nWhat happened at the loading dock?"
        
        # Stream word by word
        words = summary.split(" ")
        for i in range(0, len(words), 3):
            chunk = " ".join(words[i:i+3]) + " "
            yield chunk
            await asyncio.sleep(0.08)
        return

    # Call OpenAI / Anthropic
    history_msgs = []
    for turn in history:
        history_msgs.append({"role": turn["role"], "content": turn["content"]})
        
    results_summary = json.dumps([{
        "camera_id": r["camera_id"],
        "timestamp_ms": r["timestamp_ms"],
        "score": r["score"],
        "description": r["raw_labels"]["description"],
        "classes": r["object_classes"]
    } for r in results])

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        *history_msgs,
        {"role": "user", "content": f"User Search Query: {query}\nDatabase Search Results (JSON):\n{results_summary}"}
    ]

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL_OPENAI,
            messages=messages,
            max_tokens=600,
            temperature=0.3,
            stream=True
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        logger.error("LLM Chat completion failed", error=str(e))
        yield f"I encountered an error querying the model provider: {str(e)}."

# Custom sentence boundary stream chunker
async def stream_sentence_chunks(async_generator):
    buffer = ""
    sentence_end_re = re.compile(r'([^.!?\n]+[.!?]+(?:\s+|\Z))|([^\n]+\n)')
    async for token in async_generator:
        buffer += token
        while True:
            match = sentence_end_re.match(buffer)
            if not match:
                break
            chunk = match.group(0)
            yield chunk
            buffer = buffer[len(chunk):]
    if buffer.strip():
        yield buffer

# Workspace path resolution helper to import from packages/ai-pipeline
from pathlib import Path
sys_path_root = Path(__file__).resolve().parents[6]
ai_pipeline_src = str(sys_path_root / "packages" / "ai-pipeline" / "src")
import sys
if ai_pipeline_src not in sys.path:
    sys.path.insert(0, ai_pipeline_src)

import cv2
import pickle
import numpy as np
import torch

_yolo_model = None
_clip_encoder = None

def get_yolo_model():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        use_half = torch.cuda.is_available()
        model_path = sys_path_root / "packages" / "ai-pipeline" / "yolo11m.pt"
        model_path_str = str(model_path.resolve()) if model_path.exists() else "yolo11m.pt"
        logger.info("Loading YOLOv11m model for video search upload", path=model_path_str, device=device)
        _yolo_model = YOLO(model_path_str)
        _yolo_model.to(device)
        if use_half:
            try:
                _yolo_model.half()
            except Exception:
                pass
    return _yolo_model

def get_clip_encoder():
    global _clip_encoder
    if _clip_encoder is None:
        from embeddings.clip_encoder import CLIPEncoder
        _clip_encoder = CLIPEncoder(model_name="ViT-B-32")
    return _clip_encoder

# Bounding box schemas
ALLOWED_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

def _process_video_sync(video_path: str):
    """Processes video frames, extracts crops, runs CLIP zero-shot classification, and returns frames list."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Failed to open OpenCV VideoCapture")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps > 100:
        fps = 30.0

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Sample at 5 FPS to keep it fast
    sample_interval = max(1, int(fps / 5))

    logger.info("Starting GPU processing of video", path=video_path, fps=fps, total_frames=frame_count, sample_interval=sample_interval)

    yolo_model = get_yolo_model()
    clip_encoder = get_clip_encoder()

    COLOR_PROMPTS = ["red", "blue", "green", "yellow", "black", "white", "grey", "silver", "orange", "purple"]
    CLOTHING_PROMPTS = ["jacket", "shirt", "pants", "shorts", "backpack", "hat"]

    # Pre-encode zero-shot tags
    color_vectors, _, _ = clip_encoder.encode_text(COLOR_PROMPTS)
    clothing_vectors, _, _ = clip_encoder.encode_text(CLOTHING_PROMPTS)

    frames_data = []
    frame_id = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_id += 1
        # Only process sampled frames
        if frame_id % sample_interval != 0:
            continue

        timestamp_ms = (frame_id / fps) * 1000.0

        # Run YOLOv11m tracking on the frame
        results = yolo_model.track(
            source=frame,
            persist=True,
            conf=0.30,
            iou=0.45,
            classes=[0, 1, 2, 3, 5, 7],
            verbose=False
        )

        detections = []
        h, w = frame.shape[:2]

        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                if cls_id not in ALLOWED_CLASSES:
                    continue

                conf = round(float(boxes.conf[i].item()), 2)
                xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                track_id = int(boxes.id[i].item()) if boxes.id is not None else None

                # Clamp coordinates
                x1 = max(0, xyxy[0])
                y1 = max(0, xyxy[1])
                x2 = min(w, xyxy[2])
                y2 = min(h, xyxy[3])

                # Bounding box width/height safety check
                if (x2 - x1) < 10 or (y2 - y1) < 10:
                    continue

                # Crop object and convert BGR -> RGB for CLIP
                crop = frame[y1:y2, x1:x2]
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                
                # Get CLIP Embedding
                crop_emb, _, _ = clip_encoder.encode_image([crop_rgb])

                # Zero-shot classification for attributes
                color_sims = np.dot(color_vectors, crop_emb[0])
                predicted_color = COLOR_PROMPTS[np.argmax(color_sims)]

                clothing_sims = np.dot(clothing_vectors, crop_emb[0])
                predicted_clothing = CLOTHING_PROMPTS[np.argmax(clothing_sims)]

                detections.append({
                    "label": ALLOWED_CLASSES[cls_id],
                    "bbox": [x1 / w, y1 / h, x2 / w, y2 / h], # normalized [xmin, ymin, xmax, ymax]
                    "confidence": conf,
                    "track_id": track_id,
                    "embedding": crop_emb[0], # numpy array
                    "color": predicted_color,
                    "clothing": predicted_clothing
                })

        # Encode full frame for overall description similarity
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_emb, _, _ = clip_encoder.encode_image([frame_rgb])

        # Generate summary description text
        items = []
        for d in detections:
            desc = d["label"]
            if d["label"] == "person":
                desc = f"person wearing {d['clothing']}"
            elif d["label"] in ["car", "truck", "motorcycle", "bus"]:
                desc = f"{d['color']} {d['label']}"
            items.append(desc)

        if items:
            description = "Frame contains: " + ", ".join(items)
        else:
            description = "Empty scene"

        frames_data.append({
            "frame_number": frame_id,
            "timestamp_ms": timestamp_ms,
            "detections": detections,
            "frame_embedding": frame_emb[0],
            "description": description
        })

    cap.release()
    logger.info("GPU processing of video completed", path=video_path, processed_frames=len(frames_data))
    return frames_data

@router.post("/upload-video")
async def upload_video(
    file: UploadFile = File(...),
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Saves uploaded video, processes it on GPU with YOLOv11m and CLIP, and caches results."""
    user_payload = await authenticate_ws(token, db)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed."
        )

    # 1. Save uploaded file to public uploads folder
    video_id = str(uuid.uuid4())
    upload_dir = sys_path_root / "apps" / "web" / "public" / "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    video_path = upload_dir / f"uploaded_{video_id}.mp4"

    try:
        content = await file.read()
        with open(video_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error("Failed to save uploaded video file", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save video: {str(e)}"
        )

    # 2. Run video processing asynchronously in thread pool
    try:
        loop = asyncio.get_running_loop()
        frames_data = await loop.run_in_executor(
            None, 
            _process_video_sync, 
            str(video_path)
        )
        
        # Save processed frame data to a pickle file
        storage_dir = sys_path_root / "apps" / "api" / "app" / "storage"
        os.makedirs(storage_dir, exist_ok=True)
        pickle_path = storage_dir / f"video_{video_id}.pkl"
        with open(pickle_path, "wb") as f:
            pickle.dump(frames_data, f)
            
    except Exception as e:
        logger.error("Failed to process uploaded video", error=str(e))
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process video: {str(e)}"
        )

    return {
        "video_id": video_id,
        "video_url": f"/uploads/uploaded_{video_id}.mp4",
        "filename": file.filename
    }

async def search_uploaded_video(query: str, video_id: str) -> List[Dict[str, Any]]:
    """Searches the processed frames of the uploaded video using CLIP similarity and class overlap."""
    storage_dir = sys_path_root / "apps" / "api" / "app" / "storage"
    pickle_path = storage_dir / f"video_{video_id}.pkl"
    if not pickle_path.exists():
        logger.warning("Uploaded video pkl file not found", video_id=video_id)
        return []

    try:
        with open(pickle_path, "rb") as f:
            frames_data = pickle.load(f)
    except Exception as e:
        logger.error("Failed to load uploaded video pkl file", error=str(e))
        return []

    clip_encoder = get_clip_encoder()
    query_vector, _, _ = clip_encoder.encode_text([query])
    query_vector_np = query_vector[0]

    query_lower = query.lower()
    target_class = None
    for cls in ALLOWED_CLASSES.values():
        if cls in query_lower:
            target_class = cls
            break
            
    if "guy" in query_lower or "person" in query_lower or "man" in query_lower or "woman" in query_lower:
        target_class = "person"
    elif "car" in query_lower or "suv" in query_lower or "sedan" in query_lower:
        target_class = "car"
    elif "truck" in query_lower or "tempo" in query_lower:
        target_class = "truck"
    elif "bike" in query_lower or "motorcycle" in query_lower:
        target_class = "motorcycle"

    scored_frames = []
    for frame in frames_data:
        full_frame_similarity = np.dot(query_vector_np, frame["frame_embedding"])
        
        max_crop_similarity = -1.0
        matching_crop_count = 0
        color_match = False
        
        for d in frame["detections"]:
            sim = np.dot(query_vector_np, d["embedding"])
            if sim > max_crop_similarity:
                max_crop_similarity = sim
            
            class_match = (target_class == d["label"]) if target_class else True
            
            has_color = d["color"] in query_lower
            has_clothing = d["clothing"] in query_lower
            
            if sim > 0.22 and class_match:
                matching_crop_count += 1
                if has_color or has_clothing:
                    color_match = True

        score = max(max_crop_similarity, 0.0) * 0.6 + max(full_frame_similarity, 0.0) * 0.4
        
        if target_class:
            has_class_det = any(d["label"] == target_class for d in frame["detections"])
            if has_class_det:
                score += 0.15
                
        if color_match:
            score += 0.20

        if "2 " in query_lower or "two " in query_lower:
            if matching_crop_count >= 2:
                score += 0.25
        elif "3 " in query_lower or "three " in query_lower:
            if matching_crop_count >= 3:
                score += 0.25

        scored_frames.append((score, frame))

    scored_frames.sort(key=lambda x: x[0], reverse=True)
    top_matches = [item for item in scored_frames if item[0] >= 0.20][:8]

    results = []
    for score, frame in top_matches:
        results.append({
            "id": f"uploaded-{video_id}-{frame['frame_number']}",
            "camera_id": "Uploaded Video",
            "timestamp_ms": frame["timestamp_ms"],
            "frame_number": frame["frame_number"],
            "segment_id": f"uploaded-{video_id}",
            "object_classes": list(set(d["label"] for d in frame["detections"])),
            "score": float(score),
            "raw_labels": {
                "detections": [
                    {
                        "label": d["label"],
                        "bbox": d["bbox"],
                        "attributes": {
                            "color": d["color"],
                            "clothing": d["clothing"]
                        }
                    } for d in frame["detections"]
                ],
                "description": frame["description"],
                "video_path": f"/uploads/uploaded_{video_id}.mp4"
            }
        })
        
    return results

CAMERA_NAMES = {
    "cam-lobby": "Lobby Entrance Camera",
    "cam-parking": "Parking Lot West Feed",
    "cam-roadway": "Roadway Intersection North",
    "cam-dock": "Dock Loading Bay Area",
}

@router.websocket("/ws")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint supporting authenticated multi-turn conversational video search."""
    await websocket.accept()
    
    # 1. Authenticate JWT token
    user_payload = await authenticate_ws(token, db)
    if not user_payload:
        logger.warning("WS Connection rejected: Authentication failed")
        await websocket.close(code=1008) # Policy Violation
        return

    redis_client = get_redis_client()
    session_id = None
    
    try:
        while True:
            # Receive text message
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
            except ValueError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON payload format."}))
                continue

            query = data.get("text", "").strip()
            session_id = data.get("session_id", "default_session").strip()
            video_id = data.get("video_id")

            if not query:
                await websocket.send_text(json.dumps({"type": "error", "message": "Message text cannot be empty."}))
                continue

            # 2. Rate Limiting check (100 per hour)
            is_allowed = await check_rate_limit(user_payload.sub, redis_client)
            if not is_allowed:
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": "Rate limit exceeded. Maximum 100 queries/hour."
                }))
                continue

            # 3. Prompt Injection check
            if is_prompt_injection(query):
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": "Potential prompt injection detected. Query rejected."
                }))
                continue

            # 4. Fetch conversation history from Redis (last 10 turns = 20 messages max)
            history_key = f"chat_history:{session_id}"
            history_bytes = None
            if redis_client:
                try:
                    history_bytes = await redis_client.get(history_key)
                except Exception as e:
                    logger.warning("Failed to fetch conversation history from Redis", error=str(e))
            history = []
            if history_bytes:
                try:
                    if isinstance(history_bytes, str):
                        history_bytes = history_bytes.encode()
                    history = decrypt_history(history_bytes)
                except Exception as e:
                    logger.error("Failed to decrypt history, starting fresh", error=str(e))

            # 5. Multi-turn query refinement
            refined_query = await query_llm_refinement(query, history)
            logger.info("Refined query", raw=query, refined=refined_query)

            # 6. Retrieve search results (check if uploaded video search is active)
            if video_id:
                results = await search_uploaded_video(refined_query, video_id)
                intent_dict = {
                    "intent_type": "search",
                    "object_class": "various",
                    "camera_ids": ["Uploaded Video"],
                    "time_range": {"description": "Uploaded Video timeline"},
                    "negations": [],
                    "rewritten_query": f"uploaded video search: {refined_query}"
                }
            else:
                intent = await nlu_parser.parse(refined_query)
                intent_dict = intent.to_dict() if hasattr(intent, "to_dict") else {}
                
                from app.services.query_parser import ParsedQuery
                classes = [intent.object_class] if intent.object_class else []
                start_time = intent.time_range.get("start_ms") if intent.time_range else None
                end_time = intent.time_range.get("end_ms") if intent.time_range else None

                parsed_query = ParsedQuery(
                    raw_query=intent.raw_query,
                    semantic_query=intent.rewritten_query or intent.raw_query,
                    classes=classes,
                    excluded_classes=intent.negations,
                    start_time=start_time,
                    end_time=end_time,
                    camera_ids=intent.camera_ids,
                    spatial_zone=intent.spatial_zone,
                    expanded_synonyms=[]
                )

                allowed_cams = await get_allowed_camera_ids(
                    user_payload.tenant_id, 
                    user_payload.role, 
                    user_payload.sub, 
                    db
                )
                
                search_res = await vector_search_service.search(
                    query_text=refined_query,
                    user_allowed_cameras=allowed_cams,
                    parsed_query_override=parsed_query
                )
                results = search_res.get("results", [])

            # Immediately send search results so frontend grid updates
            await websocket.send_text(json.dumps({
                "type": "search_results",
                "results": results,
                "intent": intent_dict
            }))

            # 7. Query LLM generator stream
            raw_stream = fetch_llm_stream(refined_query, history, results)
            
            # Sentence chunk boundary streaming to satisfy low-latency sentence boundary requirements
            chunked_stream = stream_sentence_chunks(raw_stream)
            
            accumulated_response = ""
            async for sentence in chunked_stream:
                accumulated_response += sentence
                await websocket.send_text(json.dumps({
                    "type": "content_chunk",
                    "text": sentence
                }))

            # 8. Post-process suggestions from LLM output
            suggestions = []
            if "[SUGGESTIONS]" in accumulated_response:
                parts = accumulated_response.split("[SUGGESTIONS]")
                accumulated_response = parts[0].strip()
                if len(parts) > 1:
                    suggestions = [s.strip() for s in parts[1].split("\n") if s.strip()]

            # Clean and cap at 3 suggestions
            suggestions = [s for s in suggestions if not s.startswith("[")][:3]
            if not suggestions:
                # Fallback suggestions if LLM output fails
                suggestions = ["Show only White SUVs", "Search lobby entrance", "Search loading dock"]

            # Send suggestions
            await websocket.send_text(json.dumps({
                "type": "suggestions",
                "suggestions": suggestions
            }))

            # 9. Update encrypted conversation history (keep last 20 messages / 10 turns)
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": accumulated_response})
            history = history[-20:]
            
            if redis_client:
                try:
                    encrypted_data = encrypt_history(history)
                    # Save with 90-day TTL (7776000 seconds)
                    await redis_client.setex(history_key, 7776000, encrypted_data)
                except Exception as e:
                    logger.warning("Failed to save conversation history to Redis", error=str(e))

            # 10. Audit log for compliance
            audit_log_chat(user_payload.sub, user_payload.tenant_id, query, accumulated_response)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", session_id=session_id)
    except Exception as e:
        logger.error("Error in websocket session", error=str(e))
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": f"Server error occurred: {str(e)}"}))
        except Exception:
            pass
