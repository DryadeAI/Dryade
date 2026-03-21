"""File Safety Management Endpoints.

Provides on-demand file scanning, quarantine management, and scan statistics.
The file safety system uses a dual-scanner architecture:

Scanners:
- ClamAV: Signature-based virus/malware detection
- YARA: Rule-based pattern matching for custom threat detection

Both scanners run in parallel for comprehensive coverage. Files failing
either scanner are rejected and optionally quarantined.

Target: ~140 LOC
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func

from core.api.models.openapi import response_with_errors
from core.database.models import FileScanResult
from core.database.session import get_session
import core.extensions as _extensions
from core.logs import get_logger

router = APIRouter(tags=["files"])
logger = get_logger(__name__)

class ScannerResult(BaseModel):
    """Result from a single scanner (ClamAV or YARA)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "safe": True,
                "threats": [],
                "scanner": "clamav",
                "scan_time": 0.125,
                "error": None,
            }
        }
    )

    safe: bool = Field(..., description="True if scanner found no threats")
    threats: list[str] = Field(..., description="List of detected threat names/signatures")
    scanner: str = Field(..., description="Scanner name (clamav or yara)")
    scan_time: float = Field(..., ge=0.0, description="Scan duration in seconds")
    error: str | None = Field(None, description="Error message if scan failed")

class ScanResultResponse(BaseModel):
    """Combined scan result from both ClamAV and YARA scanners."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_path": "/tmp/upload.pdf",
                "safe": True,
                "clamav_result": {
                    "safe": True,
                    "threats": [],
                    "scanner": "clamav",
                    "scan_time": 0.12,
                },
                "yara_result": {"safe": True, "threats": [], "scanner": "yara", "scan_time": 0.05},
                "combined_threats": [],
                "scan_time": 0.17,
            }
        }
    )

    file_path: str = Field(..., description="Absolute path to the scanned file")
    safe: bool = Field(..., description="True only if BOTH scanners found no threats")
    clamav_result: dict[str, Any] = Field(
        ..., description="ClamAV scanner results (signature-based detection)"
    )
    yara_result: dict[str, Any] = Field(
        ..., description="YARA scanner results (rule-based pattern matching)"
    )
    combined_threats: list[str] = Field(
        ..., description="All threats from both scanners, prefixed with scanner name"
    )
    scan_time: float = Field(
        ..., ge=0.0, description="Total scan time in seconds (both scanners combined)"
    )

class UploadScanResponse(BaseModel):
    """Response for file upload and scan operation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "accepted",
                "filename": "document.pdf",
                "size": 102400,
                "threats": [],
                "message": "File passed security scan",
            }
        }
    )

    status: str = Field(..., description="Result status: 'accepted' or 'rejected'")
    filename: str = Field(..., description="Original filename")
    size: int | None = Field(None, ge=0, description="File size in bytes (only for accepted files)")
    threats: list[str] | None = Field(
        None, description="Detected threats (only for rejected files)"
    )
    message: str = Field(..., description="Human-readable result message")

class QuarantineFileInfo(BaseModel):
    """Information about a quarantined file."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "malicious.exe",
                "original_path": "/uploads/malicious.exe",
                "quarantine_time": "2026-01-13T12:00:00Z",
                "threats": ["Win.Trojan.Generic"],
                "size_bytes": 45678,
            }
        }
    )

    filename: str = Field(..., description="Filename in quarantine directory")
    original_path: str = Field(..., description="Original file path before quarantine")
    quarantine_time: str = Field(..., description="ISO 8601 timestamp when file was quarantined")
    threats: list[str] = Field(..., description="Threats that triggered quarantine")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")

class ScanStatsResponse(BaseModel):
    """File scanning statistics and scanner status."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_scans": 150,
                "threats_detected": 3,
                "quarantined_files": 3,
                "average_scan_time": 0.18,
                "clamav_enabled": True,
                "yara_enabled": True,
            }
        }
    )

    total_scans: int = Field(..., ge=0, description="Total number of file scans performed")
    threats_detected: int = Field(..., ge=0, description="Total number of threats detected")
    quarantined_files: int = Field(..., ge=0, description="Number of files currently in quarantine")
    average_scan_time: float = Field(..., ge=0.0, description="Average scan duration in seconds")
    clamav_enabled: bool = Field(..., description="Whether ClamAV scanner is enabled and available")
    yara_enabled: bool = Field(..., description="Whether YARA scanner is enabled and available")

class ReleaseResponse(BaseModel):
    """Response after releasing a file from quarantine."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "document.pdf",
                "restored_path": "/uploads/document.pdf",
                "message": "File successfully released from quarantine",
            }
        }
    )

    filename: str = Field(..., description="Name of released file")
    restored_path: str = Field(..., description="Path where file was restored")
    message: str = Field(..., description="Human-readable result message")

def _find_quarantine_file(quarantine_dir: Path, file_id: str) -> Path | None:
    """Find a quarantined file by ID (filename or partial match)."""
    for file_path in quarantine_dir.glob("*"):
        if file_path.suffix == ".meta":
            continue
        if file_path.name == file_id or file_path.stem == file_id:
            return file_path
    return None

@router.post(
    "/scan",
    response_model=ScanResultResponse,
    responses=response_with_errors(400, 404, 500, 503),
    summary="Scan file for threats",
    description="Scan a file using ClamAV and YARA scanners.",
)
async def scan_file(
    file_path: str = Body(..., embed=True, description="Absolute path to the file to scan"),
):
    """Scan a file with ClamAV and YARA.

    Dual-Scanner Architecture:
    - ClamAV: Signature-based detection for known malware
    - YARA: Rule-based pattern matching for custom threats

    Both scanners run in parallel. A file is considered safe only if
    both scanners report no threats.

    Returns detailed results from both scanners including scan times.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}"
            )

        # Run combined scan
        clamav_result, yara_result = await _extensions.scan_file_combined(str(path))

        # Combine threats
        threats = []
        if not clamav_result.safe:
            threats.extend([f"ClamAV: {t}" for t in clamav_result.threats])
        if not yara_result.safe:
            threats.extend([f"YARA: {t}" for t in yara_result.threats])

        total_scan_time = clamav_result.scan_time + yara_result.scan_time

        return ScanResultResponse(
            file_path=file_path,
            safe=clamav_result.safe and yara_result.safe,
            clamav_result={
                "safe": clamav_result.safe,
                "threats": clamav_result.threats,
                "scanner": clamav_result.scanner,
                "scan_time": clamav_result.scan_time,
                "error": clamav_result.error,
            },
            yara_result={
                "safe": yara_result.safe,
                "threats": yara_result.threats,
                "scanner": yara_result.scanner,
                "scan_time": yara_result.scan_time,
                "error": yara_result.error,
            },
            combined_threats=threats,
            scan_time=total_scan_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to scan file {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Scan failed: {str(e)}"
        ) from e

@router.post(
    "/upload-and-scan",
    response_model=UploadScanResponse,
    responses=response_with_errors(400, 500, 503),
    summary="Upload and scan file",
    description="Upload a file, scan it, and return results. Infected files are rejected.",
)
async def upload_and_scan(file: UploadFile = File(..., description="File to upload and scan")):
    """Upload a file and scan it before accepting.

    Process:
    1. Save uploaded file to temporary location
    2. Run ClamAV and YARA scans
    3. Return 'accepted' if clean, 'rejected' if threats found
    4. Clean up temporary file

    Rejected files are NOT saved. Use this endpoint for secure file
    uploads that must pass malware scanning.
    """
    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(file.filename).suffix
        ) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Scan the file
            safe, threats = await _extensions.is_file_safe(tmp_file_path)

            if not safe:
                logger.warning(f"Uploaded file {file.filename} contains threats: {threats}")
                return {
                    "status": "rejected",
                    "filename": file.filename,
                    "threats": threats,
                    "message": "File rejected due to malware detection",
                }

            return {
                "status": "accepted",
                "filename": file.filename,
                "size": len(content),
                "message": "File passed security scan",
            }

        finally:
            # Clean up temp file
            Path(tmp_file_path).unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Failed to scan uploaded file {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload scan failed: {str(e)}",
        ) from e

@router.get(
    "/quarantine",
    response_model=list[QuarantineFileInfo],
    responses=response_with_errors(500),
    summary="List quarantined files",
    description="Returns information about all files in quarantine.",
)
async def list_quarantine():
    """List all quarantined files.

    Quarantined files are malicious files that were detected and moved
    to a safe location instead of being deleted.

    Each entry includes:
    - Original file path
    - Threats that triggered quarantine
    - Quarantine timestamp
    - File size

    Use for security auditing and incident investigation.
    """
    try:
        scanner = _extensions.get_clamav_scanner()
        quarantine_dir = scanner._quarantine_dir

        if not quarantine_dir.exists():
            return []

        quarantined = []
        for file_path in quarantine_dir.glob("*"):
            # Skip metadata files
            if file_path.suffix == ".meta":
                continue

            # Read metadata if exists
            meta_path = file_path.with_suffix(file_path.suffix + ".meta")
            original_path = "unknown"
            quarantine_time = "unknown"
            threats = []

            if meta_path.exists():
                meta_content = meta_path.read_text()
                for line in meta_content.split("\n"):
                    if line.startswith("Original path:"):
                        original_path = line.split(":", 1)[1].strip()
                    elif line.startswith("Quarantine time:"):
                        quarantine_time = line.split(":", 1)[1].strip()
                    elif line.startswith("Threats:"):
                        threats = [t.strip() for t in line.split(":", 1)[1].split(",")]

            quarantined.append(
                QuarantineFileInfo(
                    filename=file_path.name,
                    original_path=original_path,
                    quarantine_time=quarantine_time,
                    threats=threats,
                    size_bytes=file_path.stat().st_size,
                )
            )

        return quarantined

    except Exception as e:
        logger.error(f"Failed to list quarantine: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list quarantine: {str(e)}",
        ) from e

@router.get(
    "/scan_stats",
    response_model=ScanStatsResponse,
    responses=response_with_errors(500),
    summary="Get scan statistics",
    description="Returns file scanning metrics and scanner availability status.",
)
async def get_scan_stats():
    """Get file scanning statistics.

    Returns:
    - Total scans performed
    - Threats detected and quarantined
    - Average scan time
    - Scanner availability (ClamAV, YARA)

    Use for monitoring scanner health and security dashboard metrics.
    """
    try:
        clamav_scanner = _extensions.get_clamav_scanner()
        yara_scanner = _extensions.get_yara_scanner()
        quarantine_dir = clamav_scanner._quarantine_dir

        # Count quarantined files
        quarantined_count = 0
        if quarantine_dir.exists():
            quarantined_count = len([f for f in quarantine_dir.glob("*") if f.suffix != ".meta"])

        # Query database for scan statistics
        with get_session() as session:
            # Total scans
            total_scans = session.query(func.count(FileScanResult.id)).scalar() or 0

            # Threats detected (files where either scanner found issues)
            threats_detected = (
                session.query(func.count(FileScanResult.id))
                .filter((not FileScanResult.clamav_safe) | (not FileScanResult.yara_safe))
                .scalar()
                or 0
            )

            # Average scan time
            avg_scan_time = (
                session.query(func.avg(FileScanResult.scan_time))
                .filter(FileScanResult.scan_time.isnot(None))
                .scalar()
                or 0.0
            )

            return ScanStatsResponse(
                total_scans=total_scans,
                threats_detected=threats_detected,
                quarantined_files=quarantined_count,
                average_scan_time=avg_scan_time,
                clamav_enabled=clamav_scanner._enabled,
                yara_enabled=yara_scanner._enabled,
            )

    except Exception as e:
        logger.error(f"Failed to get scan stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}",
        ) from e

@router.post(
    "/quarantine/{file_id}/release",
    response_model=ReleaseResponse,
    responses=response_with_errors(404, 500),
    summary="Release file from quarantine",
    description="Restore a quarantined file to its original location (for false positives).",
)
async def release_quarantined(file_id: str):
    """Release a file from quarantine back to its original location.

    Use this for false positives where manual review confirms the file is safe.
    The file is moved from quarantine to its original path.

    Warning: Only release files after thorough manual verification.
    """
    try:
        scanner = _extensions.get_clamav_scanner()
        quarantine_dir = scanner._quarantine_dir

        # Find the file in quarantine
        file_path = _find_quarantine_file(quarantine_dir, file_id)
        if file_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found in quarantine: {file_id}",
            )

        # Read metadata to get original path
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        original_path = None

        if meta_path.exists():
            meta_content = meta_path.read_text()
            for line in meta_content.split("\n"):
                if line.startswith("Original path:"):
                    original_path = line.split(":", 1)[1].strip()
                    break

        if original_path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cannot release: original path not found in metadata",
            )

        # Ensure parent directory exists
        original_path_obj = Path(original_path)
        original_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Move file back to original location
        shutil.move(str(file_path), original_path)

        # Delete metadata file
        meta_path.unlink(missing_ok=True)

        logger.info(f"Released quarantined file {file_id} to {original_path}")

        return ReleaseResponse(
            filename=file_path.name,
            restored_path=original_path,
            message="File successfully released from quarantine",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to release quarantined file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release file: {str(e)}",
        ) from e

@router.delete(
    "/quarantine/{file_id}",
    status_code=204,
    responses=response_with_errors(404, 500),
    summary="Permanently delete quarantined file",
    description="Permanently delete a file from quarantine. This action is irreversible.",
)
async def delete_quarantined(file_id: str):
    """Permanently delete a quarantined file.

    Removes both the quarantined file and its metadata file.
    This action is irreversible - the file cannot be recovered.

    Use this for confirmed malicious files that should be destroyed.
    """
    try:
        scanner = _extensions.get_clamav_scanner()
        quarantine_dir = scanner._quarantine_dir

        # Find the file in quarantine
        file_path = _find_quarantine_file(quarantine_dir, file_id)
        if file_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found in quarantine: {file_id}",
            )

        # Delete the file
        file_path.unlink()

        # Delete metadata file if exists
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        meta_path.unlink(missing_ok=True)

        logger.info(f"Permanently deleted quarantined file {file_id}")

        # Return 204 No Content (handled by status_code=204)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete quarantined file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        ) from e
