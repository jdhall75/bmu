"""Tests for kiroku.parsers."""

import pytest

from kiroku.parsers import parse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEXTFSM_TEMPLATE = """\
Value HOSTNAME (\\S+)
Value VERSION (\\S+)

Start
  ^hostname\\s+${HOSTNAME}
  ^version\\s+${VERSION} -> Record

EOF"""

TEXTFSM_PAYLOAD = "hostname router1\nversion 15.2"

TTP_TEMPLATE = "hostname {{ hostname }}"
TTP_PAYLOAD = "hostname router1"

XML_PAYLOAD = "<root><item>hello</item></root>"
XSLT_STYLESHEET = """\
<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="text"/>
  <xsl:template match="/root/item">
    <xsl:value-of select="."/>
  </xsl:template>
</xsl:stylesheet>"""


# ---------------------------------------------------------------------------
# parse() dispatch
# ---------------------------------------------------------------------------


def test_none_parser_type_returns_none():
    assert parse(None, "body", "payload") is None


def test_none_body_returns_none():
    assert parse("textfsm", None, "payload") is None


def test_unknown_parser_type_raises():
    with pytest.raises(ValueError, match="unknown parser type"):
        parse("genie", "body", "payload")


# ---------------------------------------------------------------------------
# TextFSM
# ---------------------------------------------------------------------------


def test_textfsm_returns_list_of_dicts():
    result = parse("textfsm", TEXTFSM_TEMPLATE, TEXTFSM_PAYLOAD)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["HOSTNAME"] == "router1"
    assert result[0]["VERSION"] == "15.2"


def test_textfsm_empty_payload_returns_empty_list():
    result = parse("textfsm", TEXTFSM_TEMPLATE, "")
    assert result == []


def test_textfsm_multiple_records():
    payload = "hostname r1\nversion 12.0\nhostname r2\nversion 15.2"
    result = parse("textfsm", TEXTFSM_TEMPLATE, payload)
    assert len(result) == 2
    assert result[0]["HOSTNAME"] == "r1"
    assert result[1]["HOSTNAME"] == "r2"


def test_textfsm_bad_template_raises():
    with pytest.raises(Exception):
        parse("textfsm", "not a valid textfsm template", "any payload")


# ---------------------------------------------------------------------------
# TTP
# ---------------------------------------------------------------------------


def test_ttp_returns_result():
    result = parse("ttp", TTP_TEMPLATE, TTP_PAYLOAD)
    assert result is not None


def test_ttp_parses_hostname():
    result = parse("ttp", TTP_TEMPLATE, TTP_PAYLOAD)
    # _ttp unwraps the outer [[...]] wrapper, so result is [{...}]
    assert result[0].get("hostname") == "router1"


# ---------------------------------------------------------------------------
# XSLT
# ---------------------------------------------------------------------------


def test_xslt_returns_dict_with_transformed_key():
    result = parse("xslt", XSLT_STYLESHEET, XML_PAYLOAD)
    assert isinstance(result, dict)
    assert "transformed" in result


def test_xslt_transformation_output():
    result = parse("xslt", XSLT_STYLESHEET, XML_PAYLOAD)
    assert "hello" in result["transformed"]


def test_xslt_bad_xml_raises():
    with pytest.raises(Exception):
        parse("xslt", XSLT_STYLESHEET, "not xml at all")


def test_xslt_bad_stylesheet_raises():
    with pytest.raises(Exception):
        parse("xslt", "<bad/>", XML_PAYLOAD)


# ---------------------------------------------------------------------------
# parse library (_parse_lib)
# ---------------------------------------------------------------------------

PARSE_TEMPLATE = "hostname {hostname}"
PARSE_PAYLOAD = "hostname router1"


def test_parse_lib_dispatch():
    result = parse("parse", PARSE_TEMPLATE, PARSE_PAYLOAD)
    assert result is not None


def test_parse_lib_named_fields():
    result = parse("parse", PARSE_TEMPLATE, PARSE_PAYLOAD)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["hostname"] == "router1"


def test_parse_lib_fixed_positional_fields():
    result = parse("parse", "{} {}", "hello world")
    assert result[0]["_0"] == "hello"
    assert result[0]["_1"] == "world"


def test_parse_lib_skips_empty_lines():
    payload = "\nhostname router1\n\nhostname router2\n"
    result = parse("parse", PARSE_TEMPLATE, payload)
    assert len(result) == 2


def test_parse_lib_skips_non_matching_lines():
    payload = "hostname router1\nversion 15.2\nhostname router2"
    result = parse("parse", PARSE_TEMPLATE, payload)
    assert len(result) == 2
    assert result[0]["hostname"] == "router1"
    assert result[1]["hostname"] == "router2"


def test_parse_lib_empty_payload():
    result = parse("parse", PARSE_TEMPLATE, "")
    assert result == []


# ---------------------------------------------------------------------------
# Juniper indicator stripping (_clean)
# ---------------------------------------------------------------------------


def test_juniper_indicator_stripped_before_textfsm():
    payload = "{master}\nhostname router1\nversion 15.2"
    result = parse("textfsm", TEXTFSM_TEMPLATE, payload)
    assert len(result) == 1
    assert result[0]["HOSTNAME"] == "router1"


def test_juniper_indicator_with_slot_stripped():
    payload = "{master:0}\nhostname router1\nversion 15.2"
    result = parse("textfsm", TEXTFSM_TEMPLATE, payload)
    assert result[0]["HOSTNAME"] == "router1"


# ---------------------------------------------------------------------------
# TTP non-standard result shape (_ttp fallback branch, line 52)
# ---------------------------------------------------------------------------


def test_ttp_fallback_when_result_not_double_wrapped():
    from unittest.mock import MagicMock, patch

    from kiroku.parsers import _ttp

    mock_instance = MagicMock()
    # Return a list whose first element is a dict (not a list), so the
    # isinstance(raw[0], list) guard is False and the fallback path runs.
    mock_instance.result.return_value = [{"hostname": "router1"}]

    with patch("ttp.ttp", return_value=mock_instance):
        result = _ttp("hostname {{ hostname }}", "hostname router1")

    assert result == [{"hostname": "router1"}]
