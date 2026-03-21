"""Tests for core/api/routes/files.py -- File Safety Management routes.

Tests route handlers for file scanning, quarantine management, and scan statistics.
All file system and scanner dependencies are mocked.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: build a mock scan result
# ---------------------------------------------------------------------------
def _make_scan_result(safe=True, threats=None, scanner="clamav", scan_time=0.1, error=None):
    return SimpleNamespace(
        safe=safe,
        threats=threats or [],
        scanner=scanner,
        scan_time=scan_time,
        error=error,
    )

# ===========================================================================
# scan_file endpoint
# ===========================================================================
class TestScanFile:
    """Tests for POST /scan."""

    @pytest.mark.asyncio
    async def test_scan_file_safe(self, tmp_path):
        """Scan a clean file -- should return safe=True with empty threats."""
        test_file = tmp_path / "clean.txt"
        test_file.write_text("hello")

        clamav_result = _make_scan_result(safe=True, scanner="clamav")
        yara_result = _make_scan_result(safe=True, scanner="yara", scan_time=0.05)

        with patch("core.api.routes.files.scan_file_combined", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = (clamav_result, yara_result)
            from core.api.routes.files import scan_file

            result = await scan_file(file_path=str(test_file))

        assert result.safe is True
        assert result.combined_threats == []
        assert result.scan_time == pytest.approx(0.15)
        assert result.clamav_result["safe"] is True
        assert result.yara_result["safe"] is True

    @pytest.mark.asyncio
    async def test_scan_file_threats_detected(self, tmp_path):
        """Scan an infected file -- should return safe=False with threats."""
        test_file = tmp_path / "bad.exe"
        test_file.write_text("malware")

        clamav_result = _make_scan_result(safe=False, threats=["Win.Trojan.X"], scanner="clamav")
        yara_result = _make_scan_result(safe=False, threats=["YARA_Rule1"], scanner="yara")

        with patch("core.api.routes.files.scan_file_combined", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = (clamav_result, yara_result)
            from core.api.routes.files import scan_file

            result = await scan_file(file_path=str(test_file))

        assert result.safe is False
        assert "ClamAV: Win.Trojan.X" in result.combined_threats
        assert "YARA: YARA_Rule1" in result.combined_threats

    @pytest.mark.asyncio
    async def test_scan_file_not_found(self):
        """Scan a missing file -- should raise 404."""
        from fastapi import HTTPException

        from core.api.routes.files import scan_file

        with pytest.raises(HTTPException) as exc_info:
            await scan_file(file_path="/nonexistent/file.txt")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_scan_file_error(self, tmp_path):
        """Scan failure -- should raise 500."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        from fastapi import HTTPException

        with patch("core.api.routes.files.scan_file_combined", new_callable=AsyncMock) as mock_scan:
            mock_scan.side_effect = RuntimeError("Scanner unavailable")
            from core.api.routes.files import scan_file

            with pytest.raises(HTTPException) as exc_info:
                await scan_file(file_path=str(test_file))
            assert exc_info.value.status_code == 500

# ===========================================================================
# upload_and_scan endpoint
# ===========================================================================
class TestUploadAndScan:
    """Tests for POST /upload-and-scan."""

    @pytest.mark.asyncio
    async def test_upload_clean_file(self):
        """Upload a clean file -- should return accepted."""
        mock_file = MagicMock()
        mock_file.filename = "clean.txt"
        mock_file.read = AsyncMock(return_value=b"hello world")

        with patch("core.api.routes.files.is_file_safe", new_callable=AsyncMock) as mock_safe:
            mock_safe.return_value = (True, [])
            from core.api.routes.files import upload_and_scan

            result = await upload_and_scan(file=mock_file)

        assert result["status"] == "accepted"
        assert result["filename"] == "clean.txt"
        assert result["size"] == 11

    @pytest.mark.asyncio
    async def test_upload_infected_file(self):
        """Upload an infected file -- should return rejected with threats."""
        mock_file = MagicMock()
        mock_file.filename = "bad.exe"
        mock_file.read = AsyncMock(return_value=b"malware payload")

        with patch("core.api.routes.files.is_file_safe", new_callable=AsyncMock) as mock_safe:
            mock_safe.return_value = (False, ["Win.Trojan.Generic"])
            from core.api.routes.files import upload_and_scan

            result = await upload_and_scan(file=mock_file)

        assert result["status"] == "rejected"
        assert result["filename"] == "bad.exe"
        assert "Win.Trojan.Generic" in result["threats"]

    @pytest.mark.asyncio
    async def test_upload_scan_failure(self):
        """Upload scan error -- should raise 500."""
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.read = AsyncMock(side_effect=RuntimeError("Upload failed"))

        from fastapi import HTTPException

        from core.api.routes.files import upload_and_scan

        with pytest.raises(HTTPException) as exc_info:
            await upload_and_scan(file=mock_file)
        assert exc_info.value.status_code == 500

# ===========================================================================
# list_quarantine endpoint
# ===========================================================================
class TestListQuarantine:
    """Tests for GET /quarantine."""

    @pytest.mark.asyncio
    async def test_list_empty_quarantine(self):
        """No quarantine dir -- should return empty list."""
        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = Path("/nonexistent/quarantine")

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import list_quarantine

            result = await list_quarantine()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_quarantine_with_files(self, tmp_path):
        """Quarantine with files -- should return file info."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()

        # Create a quarantined file
        bad_file = quarantine_dir / "bad.exe"
        bad_file.write_text("malware content")

        # Create metadata
        meta_file = quarantine_dir / "bad.exe.meta"
        meta_file.write_text(
            "Original path: /uploads/bad.exe\n"
            "Quarantine time: 2026-01-13T12:00:00Z\n"
            "Threats: Win.Trojan.Generic, YARA.Suspicious"
        )

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import list_quarantine

            result = await list_quarantine()

        assert len(result) == 1
        assert result[0].filename == "bad.exe"
        assert result[0].original_path == "/uploads/bad.exe"
        assert "Win.Trojan.Generic" in result[0].threats

    @pytest.mark.asyncio
    async def test_list_quarantine_error(self):
        """Quarantine access error -- should raise 500."""
        from fastapi import HTTPException

        with patch(
            "core.api.routes.files.get_clamav_scanner", side_effect=RuntimeError("No scanner")
        ):
            from core.api.routes.files import list_quarantine

            with pytest.raises(HTTPException) as exc_info:
                await list_quarantine()
            assert exc_info.value.status_code == 500

# ===========================================================================
# release_quarantined endpoint
# ===========================================================================
class TestReleaseQuarantined:
    """Tests for POST /quarantine/{file_id}/release."""

    @pytest.mark.asyncio
    async def test_release_not_found(self, tmp_path):
        """Release non-existent file -- should raise 404."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        from fastapi import HTTPException

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import release_quarantined

            with pytest.raises(HTTPException) as exc_info:
                await release_quarantined(file_id="nonexistent")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_release_success(self, tmp_path):
        """Release quarantined file successfully."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()
        restore_dir = tmp_path / "uploads"
        restore_dir.mkdir()

        # Create quarantined file and metadata
        bad_file = quarantine_dir / "document.pdf"
        bad_file.write_text("file content")
        meta_file = quarantine_dir / "document.pdf.meta"
        meta_file.write_text(f"Original path: {restore_dir / 'document.pdf'}\n")

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import release_quarantined

            result = await release_quarantined(file_id="document.pdf")

        assert result.filename == "document.pdf"
        assert "document.pdf" in result.restored_path

    @pytest.mark.asyncio
    async def test_release_no_metadata(self, tmp_path):
        """Release file with no metadata -- should raise 500."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()
        bad_file = quarantine_dir / "test.exe"
        bad_file.write_text("content")

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        from fastapi import HTTPException

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import release_quarantined

            with pytest.raises(HTTPException) as exc_info:
                await release_quarantined(file_id="test.exe")
            assert exc_info.value.status_code == 500

# ===========================================================================
# delete_quarantined endpoint
# ===========================================================================
class TestDeleteQuarantined:
    """Tests for DELETE /quarantine/{file_id}."""

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tmp_path):
        """Delete non-existent file -- should raise 404."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        from fastapi import HTTPException

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import delete_quarantined

            with pytest.raises(HTTPException) as exc_info:
                await delete_quarantined(file_id="nonexistent")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self, tmp_path):
        """Delete quarantined file successfully."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()
        bad_file = quarantine_dir / "virus.exe"
        bad_file.write_text("malware")
        meta_file = quarantine_dir / "virus.exe.meta"
        meta_file.write_text("Threats: Generic\n")

        mock_scanner = MagicMock()
        mock_scanner._quarantine_dir = quarantine_dir

        with patch("core.api.routes.files.get_clamav_scanner", return_value=mock_scanner):
            from core.api.routes.files import delete_quarantined

            result = await delete_quarantined(file_id="virus.exe")

        assert result is None  # 204 No Content
        assert not bad_file.exists()
        assert not meta_file.exists()

# ===========================================================================
# _find_quarantine_file helper
# ===========================================================================
class TestFindQuarantineFile:
    """Tests for the _find_quarantine_file helper."""

    def test_find_by_full_name(self, tmp_path):
        """Find file by exact filename."""
        f = tmp_path / "virus.exe"
        f.write_text("x")

        from core.api.routes.files import _find_quarantine_file

        result = _find_quarantine_file(tmp_path, "virus.exe")
        assert result is not None
        assert result.name == "virus.exe"

    def test_find_by_stem(self, tmp_path):
        """Find file by stem (no extension)."""
        f = tmp_path / "virus.exe"
        f.write_text("x")

        from core.api.routes.files import _find_quarantine_file

        result = _find_quarantine_file(tmp_path, "virus")
        assert result is not None

    def test_not_found(self, tmp_path):
        """Non-existent file returns None."""
        from core.api.routes.files import _find_quarantine_file

        result = _find_quarantine_file(tmp_path, "nonexistent")
        assert result is None

    def test_skips_meta_files(self, tmp_path):
        """Meta files are skipped during search."""
        meta = tmp_path / "file.meta"
        meta.write_text("metadata")

        from core.api.routes.files import _find_quarantine_file

        result = _find_quarantine_file(tmp_path, "file.meta")
        assert result is None

# ===========================================================================
# get_scan_stats endpoint
# ===========================================================================
class TestGetScanStats:
    """Tests for GET /scan_stats."""

    @pytest.mark.asyncio
    async def test_scan_stats_success(self, tmp_path):
        """Get scan statistics successfully."""
        quarantine_dir = tmp_path / "quarantine"
        quarantine_dir.mkdir()

        mock_clamav = MagicMock()
        mock_clamav._quarantine_dir = quarantine_dir
        mock_clamav._enabled = True

        mock_yara = MagicMock()
        mock_yara._enabled = True

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.scalar.return_value = 10
        mock_query.filter.return_value = mock_query

        # get_scan_stats does a local import of get_clamav_scanner and get_yara_scanner
        # from core.extensions, so we must patch at the extensions module level.
        with (
            patch("core.extensions.get_clamav_scanner", return_value=mock_clamav),
            patch("core.extensions.get_yara_scanner", return_value=mock_yara),
            patch("core.database.session.get_session") as mock_get_session,
        ):
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.files import get_scan_stats

            result = await get_scan_stats()

        assert result.clamav_enabled is True
        assert result.yara_enabled is True

    @pytest.mark.asyncio
    async def test_scan_stats_error(self):
        """Scan stats failure -- should raise 500."""
        from fastapi import HTTPException

        # get_scan_stats does local import from core.extensions
        with (
            patch("core.extensions.get_clamav_scanner", side_effect=RuntimeError("fail")),
            patch("core.extensions.get_yara_scanner", side_effect=RuntimeError("fail")),
        ):
            from core.api.routes.files import get_scan_stats

            with pytest.raises(HTTPException) as exc_info:
                await get_scan_stats()
            assert exc_info.value.status_code == 500
