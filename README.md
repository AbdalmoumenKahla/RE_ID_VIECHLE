# Vehicle Attendance System

A local Windows desktop prototype for registering vehicles, recognizing them in photos, recorded video, and RTSP/IP camera streams, then maintaining visit attendance in SQLite. It is a PySide6 desktop app, not a browser application: detection, tracking, matching, camera capture, storage, and the interface all run on the PC. The default detector is `yolo26m.pt` (YOLO26 Medium).

## What is implemented

- PySide6 desktop shell with Dashboard, Vehicles, Register Vehicle, Live Camera, Video Testing, Attendance History, Unknown Vehicles, and Settings.
- Local SQLite schema for vehicles, multiple visual references, embeddings, cameras, attendance sessions, detections, and unknown sightings.
- Photo registration with a YOLO vehicle crop (and clearly-labelled full-photo manual fallback).
- Video registration: local video sampling, local tracking, one representative crop/embedding for every candidate track, then staff selection and registration.
- Multiple reference images per vehicle. Removing a reference also removes its linked embedding from matching.
- YOLO vehicle detection, Ultralytics ByteTrack tracking where available, and a local centroid-tracker fallback if ByteTrack cannot initialize.
- Local Re-ID embedding and cosine matching. A local ResNet50 feature backbone is supplied for the first prototype; the Settings page accepts a better, vehicle-trained local checkpoint.
- Photo/video/RTSP recognition with bounding boxes, temporary track IDs, label, match score, performance telemetry, local recognition log, and no cloud API calls.
- Arrival/continued-presence/departure handling. `PRESENT` is opened only once per visit; a departure is written after the configurable absence timeout, using the last confirmed detection time.
- Unknown vehicle capture and promotion into a registered profile.
- History filters and UTF-8 CSV export, suitable for Excel.
- QThread workers for video scanning, photo analysis, image recognition, RTSP capture, YOLO, Re-ID, and tracking so normal source processing does not freeze the UI.

## Requirements

Windows 10/11, Python 3.10–3.12 (64-bit), and a camera/video source for practical testing. CPU inference works. An NVIDIA CUDA-compatible PyTorch installation is optional; with **Preferred device = auto**, CUDA is selected when PyTorch reports a compatible GPU. `yolo26m.pt` is the recommended accuracy/throughput balance; switch to `yolo26n.pt` for a weak CPU or `yolo26l.pt` on a capable CUDA workstation after measuring live FPS.

The first run may download pretrained YOLO/torchvision weights if they are not already stored locally. For an air-gapped deployment, place approved model files in `models/` and point Settings at their local paths before running. There are no cloud inference calls after local assets are installed.

## Run locally

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

If `py` is not found, install a supported 64-bit Python from python.org, reopen PowerShell, and repeat. For CUDA, install the PyTorch build matching the deployed NVIDIA driver from the official PyTorch selector before `pip install -r requirements.txt`.

Data created by the source version stays under `data/`:

```text
data/
  vehicle_attendance.sqlite3  # local database
  settings.json               # local preference file
  vehicles/                   # saved reference crops
  captures/unknown/           # unknown sighting crops
```

The packaged executable instead stores writable data in `%LOCALAPPDATA%\VehicleAttendance`, so it also works when installed under `Program Files`.

## Test sequence

1. Open **Register Vehicle → From photo**, select a clear single-vehicle photo, give it a name/owner, and register it.
2. Open **Video Testing → Recognize photo**, choose a second photo of the same car, and inspect its score. Add front/side/rear reference images in **Vehicles → Open profile** before testing difficult viewpoints.
3. In **Register Vehicle → From video**, scan a short parking video. Choose a unique tracked candidate, give it a name/owner, and register it.
4. In **Video Testing**, select a different video and start it. Inspect boxes, labels, scores, temporary tracks, frame telemetry, and Dashboard sessions.
5. In **Settings**, use a short departure timeout for testing. Start a video/RTSP stream, then allow the vehicle to be absent longer than the timeout. Its session should change to `LEFT` with the last confirmed detection as its departure.
6. In **Live Camera**, enter `rtsp://…`, connect, then verify the Dashboard refreshes as detections arrive.

## Recognition design and limits

The identity decision is never made from a tracking ID. The processing path is:

```text
Photo / video / RTSP → YOLO vehicle detection → ByteTrack (temporary motion track)
                      → local visual embedding → cosine match against all saved references
                      → registered vehicle or unknown → attendance session
```

A tracking ID only links frames in one source. Cross-photo, cross-video, and cross-camera identity is based on stored appearance embeddings. This is why multiple views of each vehicle are valuable.

The default threshold (`0.72`) is a starting point, not a universal truth. Tune it with the school’s camera footage. Vehicle Re-ID can be wrong because of viewpoint, lighting, very similar models, distance, compression, occlusion, small crops, modifications, or low-resolution cameras. Do not use a match alone for a high-consequence decision without human review.

### Model decision

`rafayabrar/Vehicle-Re-Identification-Using-YOLO` is a useful prototype/reference: its public README describes YOLOv8 plus a mixture of traditional and deep visual features and local SQLite storage. However, the public repository is very small and its own documentation labels MobileNet/ResNet ImageNet features as its primary deep methods, so it is not vendored as the production dependency here. This implementation uses the actively maintained Ultralytics detection/tracking interface plus a local deep embedding backbone, and exposes a local checkpoint field for a vehicle-trained Re-ID model. See the [project repository](https://github.com/rafayabrar/Vehicle-Re-Identification-Using-YOLO) and the vehicle Re-ID baseline paper, [A Strong Baseline for Vehicle Re-Identification](https://arxiv.org/abs/2104.10850), when selecting and evaluating a vehicle-trained checkpoint.

The supplied ResNet50 ImageNet feature baseline makes the workflow runnable but is not a specialized vehicle Re-ID model. Before deployment, validate a vehicle-trained model (for example an OSNet/vehicle-Re-ID checkpoint you have the rights to use) against local labelled footage, set it in Settings, then calibrate threshold, FPS, and timeout.

## Automated tests

```powershell
pytest -q
```

The tests verify database reference cleanup and arrival/departure visit lifecycle. Video/camera accuracy needs actual labelled local footage and therefore is intentionally not represented by a synthetic unit test.

## Build a Windows executable

On the deployment build machine, after installing the requirements:

```powershell
.\build_windows.ps1
```

The command creates `dist\VehicleAttendance\VehicleAttendance.exe`. Test the whole `dist\VehicleAttendance` folder on a second Windows account/machine before distribution. Keep approved local models in `models/`; the build script includes `models/` and `data/` alongside the executable. Large GPU drivers and GPU-enabled PyTorch runtimes are environment-specific and must be validated on the target PC.

## Notes for future deployment

- One camera is implemented in the UI; cameras are already a separate database entity, so a multi-camera page can be added without changing attendance schema.
- RTSP compatibility depends on credentials, codec, network reachability, and the FFmpeg support bundled with OpenCV. Test the exact camera URL using a recorded clip first.
- Store database backups outside this project folder on a scheduled basis. Videos are not stored in SQLite.
- Review Ultralytics, PyTorch, and chosen checkpoint licences before a school deployment.
