"""Tests for kiroku.cve.nvd and kiroku.cve facade."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from kiroku.cve.nvd import NvdCveClient, _extract_severity


# ---------------------------------------------------------------------------
# _extract_severity
# ---------------------------------------------------------------------------


class TestExtractSeverity:
    def test_cvss_v31_returned_first(self):
        cve = {
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}],
                "cvssMetricV30": [{"cvssData": {"baseScore": 8.0, "baseSeverity": "HIGH"}}],
            }
        }
        score, severity = _extract_severity(cve)
        assert score == 9.8
        assert severity == "CRITICAL"

    def test_falls_back_to_v30_when_v31_missing(self):
        cve = {
            "metrics": {
                "cvssMetricV30": [{"cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}}],
            }
        }
        score, severity = _extract_severity(cve)
        assert score == 7.5
        assert severity == "HIGH"

    def test_falls_back_to_v2(self):
        cve = {
            "metrics": {
                "cvssMetricV2": [{"cvssData": {"baseScore": 5.0, "baseSeverity": "MEDIUM"}}],
            }
        }
        score, severity = _extract_severity(cve)
        assert score == 5.0
        assert severity == "MEDIUM"

    def test_no_metrics_returns_none_none(self):
        score, severity = _extract_severity({})
        assert score is None
        assert severity is None

    def test_empty_metric_list_skipped(self):
        cve = {"metrics": {"cvssMetricV31": [], "cvssMetricV30": []}}
        score, severity = _extract_severity(cve)
        assert score is None
        assert severity is None

    def test_null_base_score_returns_none(self):
        cve = {
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": None, "baseSeverity": "LOW"}}],
            }
        }
        score, severity = _extract_severity(cve)
        assert score is None
        assert severity == "LOW"

    def test_score_coerced_to_float(self):
        cve = {
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": "7.3", "baseSeverity": "HIGH"}}],
            }
        }
        score, severity = _extract_severity(cve)
        assert isinstance(score, float)
        assert score == 7.3


# ---------------------------------------------------------------------------
# NvdCveClient.query_cpe
# ---------------------------------------------------------------------------


def _nvd_response(vulnerabilities: list[dict]) -> BytesIO:
    return BytesIO(json.dumps({"vulnerabilities": vulnerabilities}).encode())


def _vuln(cve_id: str, score: float, severity: str, summary: str, ref: str = "") -> dict:
    return {
        "cve": {
            "id": cve_id,
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": score, "baseSeverity": severity}}]
            },
            "descriptions": [{"lang": "en", "value": summary}],
            "references": [{"url": ref}] if ref else [],
            "published": "2024-01-01T00:00:00.000",
        }
    }


class TestNvdCveClientQueryCpe:
    def _make_client(self) -> NvdCveClient:
        return NvdCveClient(api_key=None)

    def _patch_urlopen(self, body: BytesIO):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = body.read()
        return patch("kiroku.cve.nvd.urllib.request.urlopen", return_value=mock_resp)

    def test_returns_list_of_cve_entries(self):
        client = self._make_client()
        vulns = [_vuln("CVE-2024-0001", 9.8, "CRITICAL", "A critical vuln", "https://example.com")]
        body = _nvd_response(vulns)
        with self._patch_urlopen(body):
            result = client.query_cpe("cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*")
        assert len(result) == 1
        assert result[0].cve_id == "CVE-2024-0001"
        assert result[0].cvss_v3_score == 9.8
        assert result[0].severity == "CRITICAL"
        assert result[0].summary == "A critical vuln"
        assert result[0].url == "https://example.com"

    def test_returns_empty_on_network_error(self):
        client = self._make_client()
        with patch("kiroku.cve.nvd.urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = client.query_cpe("cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*")
        assert result == []

    def test_no_vulnerabilities_returns_empty(self):
        client = self._make_client()
        body = _nvd_response([])
        with self._patch_urlopen(body):
            result = client.query_cpe("cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*")
        assert result == []

    def test_multiple_vulns_returned(self):
        client = self._make_client()
        vulns = [
            _vuln("CVE-2024-0001", 9.8, "CRITICAL", "Critical", "https://a.com"),
            _vuln("CVE-2024-0002", 5.0, "MEDIUM", "Medium", "https://b.com"),
        ]
        body = _nvd_response(vulns)
        with self._patch_urlopen(body):
            result = client.query_cpe("cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*")
        assert len(result) == 2
        assert result[0].cve_id == "CVE-2024-0001"
        assert result[1].cve_id == "CVE-2024-0002"

    def test_nvd_url_fallback_when_no_refs(self):
        client = self._make_client()
        vuln = _vuln("CVE-2024-9999", 7.0, "HIGH", "Some vuln", "")  # no ref
        body = _nvd_response([vuln])
        with self._patch_urlopen(body):
            result = client.query_cpe("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*")
        assert "nvd.nist.gov" in result[0].url
        assert "CVE-2024-9999" in result[0].url

    def test_api_key_added_to_request_header(self):
        client = NvdCveClient(api_key="myapikey123")
        body = _nvd_response([])
        captured_req = {}

        def fake_urlopen(req, timeout):
            captured_req["req"] = req
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = json.dumps({"vulnerabilities": []}).encode()
            return mock_resp

        with patch("kiroku.cve.nvd.urllib.request.urlopen", side_effect=fake_urlopen):
            client.query_cpe("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*")

        req = captured_req.get("req")
        assert req is not None
        assert req.get_header("Apikey") == "myapikey123"

    def test_no_api_key_no_header(self):
        client = NvdCveClient(api_key=None)
        body = _nvd_response([])
        captured_req = {}

        def fake_urlopen(req, timeout):
            captured_req["req"] = req
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = json.dumps({"vulnerabilities": []}).encode()
            return mock_resp

        with patch("kiroku.cve.nvd.urllib.request.urlopen", side_effect=fake_urlopen):
            client.query_cpe("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*")

        req = captured_req.get("req")
        assert req.get_header("Apikey") is None

    def test_non_english_descriptions_ignored(self):
        client = self._make_client()
        vuln = {
            "cve": {
                "id": "CVE-2024-1234",
                "metrics": {
                    "cvssMetricV31": [{"cvssData": {"baseScore": 5.0, "baseSeverity": "MEDIUM"}}]
                },
                "descriptions": [
                    {"lang": "es", "value": "Un problema"},
                    {"lang": "en", "value": "An issue"},
                ],
                "references": [],
                "published": "2024-01-01T00:00:00.000",
            }
        }
        body = _nvd_response([vuln])
        with self._patch_urlopen(body):
            result = client.query_cpe("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*")
        assert result[0].summary == "An issue"


# ---------------------------------------------------------------------------
# query_cpe facade (kiroku.cve.__init__)
# ---------------------------------------------------------------------------


class TestQueryCpeFacade:
    def test_returns_list_of_dicts(self):
        from kiroku.cve import query_cpe
        from kiroku.cve.base import CveEntry

        fake_entry = CveEntry(
            cve_id="CVE-2024-0001",
            cvss_v3_score=7.5,
            severity="HIGH",
            summary="Test",
            published_at="2024-01-01T00:00:00.000",
            url="https://nvd.nist.gov",
        )
        mock_client = MagicMock()
        mock_client.query_cpe.return_value = [fake_entry]

        mock_settings = MagicMock()
        mock_settings.nvd_api_key = None

        with patch("kiroku.config.get_settings", return_value=mock_settings), \
             patch("kiroku.cve.nvd.NvdCveClient", return_value=mock_client):
            result = query_cpe("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["cve_id"] == "CVE-2024-0001"
        assert result[0]["cvss_v3_score"] == 7.5
