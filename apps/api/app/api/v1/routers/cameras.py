import asyncio
from pathlib import Path
from typing import Dict, Optional, Set, TypedDict

import cv2
import structlog
import torch
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ultralytics import YOLO

logger = structlog.get_logger("api.cameras")
router = APIRouter(prefix="/cameras", tags=["Cameras Live Stream"])

# COCO Target Class Mapping: Class ID -> Label (Requirement 3.4)
ALLOWED_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Video files mapping: maps camera_id to public upload MP4 filename
CAMERA_VIDEO_MAPPING = {
    "cam-001": "traffic-day-night.mp4",
    "cam-002": "traffic-ip.mp4",
    "cam-003": "video-lobby.mp4",
    "cam-004": "video-parking.mp4",
    "cam-005": "video-lobby.mp4",
    "cam-006": "video-lobby.mp4",
    "cam-007": "video-parking.mp4",
    "cam-008": "traffic-ip.mp4",
}


class BoundingBoxDict(TypedDict):
    """Bounding box dictionary representing pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int


class DetectionDict(TypedDict):
    """Standardized detection dictionary schema for VisionQuery."""

    track_id: Optional[int]
    class_id: int
    class_label: str
    confidence: float
    bbox: BoundingBoxDict
    frame_id: int
    timestamp_ms: float
    camera_id: str


def validate_detection(det: dict) -> bool:
    """Validate detection fields against strict schema (Requirement 3.5)."""
    try:
        # Check required fields
        for field in [
            "class_id",
            "class_label",
            "confidence",
            "bbox",
            "frame_id",
            "timestamp_ms",
            "camera_id",
        ]:
            if field not in det:
                return False
        # Validate class_id
        if det["class_id"] not in ALLOWED_CLASSES:
            return False
        # Validate class_label
        if det["class_label"] != ALLOWED_CLASSES[det["class_id"]]:
            return False
        # Validate confidence
        if not isinstance(det["confidence"], (int, float)) or det["confidence"] < 0.35:
            return False
        # Validate bbox fields
        bbox = det["bbox"]
        for bfield in ["x1", "y1", "x2", "y2"]:
            if bfield not in bbox or not isinstance(bbox[bfield], int):
                return False
        return True
    except Exception:
        return False


class CameraStreamManager:
    """Thread-safe stream manager orchestrating cv2 frame capture and YOLO tracking (Requirement 3.6)."""

    def __init__(self):
        """Initialize CameraStreamManager and load YOLOv11m weights once."""
        # Determine device (Requirement 3.2)
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.use_half = torch.cuda.is_available()

        # Load YOLO model once at application startup (Requirement 3.2)
        workspace_root = Path(__file__).resolve().parents[6]
        model_path = workspace_root / "packages" / "ai-pipeline" / "yolo11m.pt"
        if model_path.exists():
            model_path_str = str(model_path.resolve())
        else:
            # Fallback if the file isn't found
            model_path_str = "yolo11m.pt"

        logger.info(
            "Loading YOLO model weights", path=model_path_str, device=self.device
        )
        self.model = YOLO(model_path_str)
        self.model.to(self.device)

        if self.use_half:
            try:
                self.model.half()
                logger.info("YOLO model precision set to fp16")
            except Exception as e:
                logger.warning(
                    "YOLO model half precision conversion failed, using fp32",
                    error=str(e),
                )
                self.use_half = False

        # Print Startup Log (Requirement 5.1)
        classes_str = ", ".join(
            [ALLOWED_CLASSES[i] for i in sorted(ALLOWED_CLASSES.keys())]
        )
        precision_str = "fp16" if self.use_half else "fp32"
        logger.info(
            f"YOLOv11m loaded — device={self.device}, precision={precision_str}, classes=[{classes_str}]"
        )

        # Map of camera_id -> Set of WebSocket connections
        self.subscribers: Dict[str, Set[WebSocket]] = {}
        # Map of camera_id -> Background loop Task
        self.stream_tasks: Dict[str, asyncio.Task] = {}
        # Lock for managing concurrent subscriptions/tasks
        self.lock = asyncio.Lock()

    async def subscribe(self, camera_id: str, websocket: WebSocket):
        """Add a WebSocket subscription to a camera ID stream."""
        async with self.lock:
            if camera_id not in self.subscribers:
                self.subscribers[camera_id] = set()
            self.subscribers[camera_id].add(websocket)

            # Start loop if not already running for this camera
            if (
                camera_id not in self.stream_tasks
                or self.stream_tasks[camera_id].done()
            ):
                self.stream_tasks[camera_id] = asyncio.create_task(
                    self._run_stream(camera_id)
                )
                logger.info(
                    "Started background stream loop for camera", camera_id=camera_id
                )

    async def unsubscribe(self, camera_id: str, websocket: WebSocket):
        """Remove a WebSocket subscription from a camera ID stream."""
        async with self.lock:
            if camera_id in self.subscribers:
                self.subscribers[camera_id].discard(websocket)
                if not self.subscribers[camera_id]:
                    # Stop background task if no subscribers left
                    task = self.stream_tasks.pop(camera_id, None)
                    if task:
                        task.cancel()
                        logger.info(
                            "Cancelled stream loop due to no subscribers",
                            camera_id=camera_id,
                        )

    async def unsubscribe_all(self, websocket: WebSocket):
        """Clean up all subscriptions for a disconnecting WebSocket connection."""
        async with self.lock:
            for camera_id in list(self.subscribers.keys()):
                self.subscribers[camera_id].discard(websocket)
                if not self.subscribers[camera_id]:
                    task = self.stream_tasks.pop(camera_id, None)
                    if task:
                        task.cancel()
                        logger.info(
                            "Cancelled stream loop due to no subscribers (cleanup)",
                            camera_id=camera_id,
                        )

    async def _run_stream(self, camera_id: str):
        """Infinite frame-by-frame loop feeding frames to YOLO and broadcasting detections."""
        video_name = CAMERA_VIDEO_MAPPING.get(camera_id, "video-lobby.mp4")
        workspace_root = Path(__file__).resolve().parents[6]
        video_path = workspace_root / "apps" / "web" / "public" / "uploads" / video_name

        logger.info(
            "Opening video capture source", camera_id=camera_id, path=str(video_path)
        )
        cap = cv2.VideoCapture(str(video_path.resolve()))

        if not cap.isOpened():
            logger.error(
                "Failed to open OpenCV VideoCapture source",
                camera_id=camera_id,
                path=str(video_path),
            )
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 100:
            fps = 30.0

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        frame_interval = 1.0 / fps
        frame_id = 0
        last_detections = []

        try:
            while True:
                start_time = asyncio.get_event_loop().time()

                # Check if anyone is subscribed
                async with self.lock:
                    if not self.subscribers.get(camera_id):
                        break

                ret, frame = cap.read()
                if not ret:
                    # Loop video file (Requirement 3.6)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_id += 1
                timestamp_ms = (frame_id / fps) * 1000.0

                # Run YOLO tracking on every 5th frame to reduce GPU/CPU VRAM resource load.
                # Re-use previous frame detections for intermediate frames to maintain tracking.
                if frame_id == 1 or frame_id % 5 == 0:
                    try:
                        results = await asyncio.to_thread(
                            self.model.track,
                            source=frame,
                            persist=True,
                            conf=0.35,
                            iou=0.45,
                            classes=[0, 1, 2, 3, 5, 7],
                            verbose=False,
                            half=self.use_half,
                        )
                    except Exception as e:
                        logger.error(
                            "YOLO track execution failed", camera_id=camera_id, error=str(e)
                        )
                        await asyncio.sleep(0.01)
                        continue

                    # Parse tracking results
                    detections = []
                    if results and results[0].boxes is not None:
                        boxes = results[0].boxes
                        for i in range(len(boxes)):
                            cls_id = int(boxes.cls[i].item())
                            if cls_id not in ALLOWED_CLASSES:
                                continue

                            conf = round(float(boxes.conf[i].item()), 2)
                            if conf < 0.35:
                                continue

                            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                            track_id = (
                                int(boxes.id[i].item()) if boxes.id is not None else None
                            )

                            det = {
                                "track_id": track_id,
                                "class_id": cls_id,
                                "class_label": ALLOWED_CLASSES[cls_id],
                                "confidence": conf,
                                "bbox": {
                                    "x1": int(xyxy[0]),
                                    "y1": int(xyxy[1]),
                                    "x2": int(xyxy[2]),
                                    "y2": int(xyxy[3]),
                                },
                                "frame_id": frame_id,
                                "timestamp_ms": timestamp_ms,
                                "camera_id": camera_id,
                            }

                            if validate_detection(det):
                                detections.append(det)
                    last_detections = detections
                else:
                    # Re-use last detections but update frame_id and timestamp_ms
                    detections = []
                    for det in last_detections:
                        new_det = det.copy()
                        new_det["frame_id"] = frame_id
                        new_det["timestamp_ms"] = timestamp_ms
                        detections.append(new_det)

                # Construct WebSocket Payload (Requirement 4.1)
                payload = {
                    "type": "detections",
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "timestamp_ms": timestamp_ms,
                    "fps": fps,
                    "resolution": {"width": width, "height": height},
                    "detection_count": len(detections),
                    "detections": detections,
                }

                # Temporary Logger for active monitoring (Requirement 5.3)
                logger.debug(
                    f"WS BROADCAST | camera={camera_id} | frame={frame_id} | detections={[d['class_label'] for d in detections]}"
                )

                # Broadcast payload to camera subscribers
                async with self.lock:
                    subs = list(self.subscribers.get(camera_id, []))

                for ws in subs:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        # Will be cleaned up by connection close handler or keepalive checks
                        pass

                # Yield execution and regulate streaming speed to native FPS
                elapsed_time = asyncio.get_event_loop().time() - start_time
                sleep_duration = max(0.001, frame_interval - elapsed_time)
                await asyncio.sleep(sleep_duration)

        except asyncio.CancelledError:
            logger.info("Stream processing loop cancelled", camera_id=camera_id)
        finally:
            cap.release()
            logger.info("Video capture source released", camera_id=camera_id)


# Global stream manager instance
manager = CameraStreamManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """FastAPI WebSocket connection handling incoming camera subscriptions."""
    await websocket.accept()
    logger.info("WebSocket connection established")

    subscribed_cameras = set()

    try:
        while True:
            # Await subscription message from client
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "subscribe":
                camera_ids = data.get("cameraIds", [])
                logger.info("Received subscription request", camera_ids=camera_ids)

                # Unsubscribe from any cameras no longer listed
                to_remove = subscribed_cameras - set(camera_ids)
                for cam_id in to_remove:
                    await manager.unsubscribe(cam_id, websocket)
                    subscribed_cameras.remove(cam_id)

                # Subscribe to newly requested cameras
                for cam_id in camera_ids:
                    if cam_id not in subscribed_cameras:
                        await manager.subscribe(cam_id, websocket)
                        subscribed_cameras.add(cam_id)

            elif msg_type == "unsubscribe":
                camera_ids = data.get("cameraIds", [])
                for cam_id in camera_ids:
                    if cam_id in subscribed_cameras:
                        await manager.unsubscribe(cam_id, websocket)
                        subscribed_cameras.remove(cam_id)

    except WebSocketDisconnect:
        logger.info("WebSocket connection disconnected by client")
    except Exception as e:
        logger.error("WebSocket connection error occurred", error=str(e))
    finally:
        # Cleanup all subscriptions for this connection
        await manager.unsubscribe_all(websocket)
