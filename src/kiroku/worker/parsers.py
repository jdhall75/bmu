"""Parser pipeline: TextFSM, TTP, XSLT."""
from __future__ import annotations

import io


def parse(parser_type: str | None, body: str | None, payload: str) -> list[dict] | dict | None:
    if not parser_type or not body:
        return None
    if parser_type == "textfsm":
        return _textfsm(body, payload)
    if parser_type == "ttp":
        return _ttp(body, payload)
    if parser_type == "xslt":
        return _xslt(body, payload)
    raise ValueError(f"unknown parser type: {parser_type!r}")


def _textfsm(template: str, payload: str) -> list[dict]:
    import textfsm

    fsm = textfsm.TextFSM(io.StringIO(template))
    rows = fsm.ParseText(payload)
    return [dict(zip(fsm.header, r)) for r in rows]


def _ttp(template: str, payload: str) -> list[dict] | dict:
    from ttp import ttp as ttp_mod

    parser = ttp_mod(data=payload, template=template)
    parser.parse()
    # result() returns [[group1, group2, ...]] — flatten the outer wrapper list.
    raw = parser.result()
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
        return raw[0]
    return raw


def _xslt(stylesheet: str, payload: str) -> dict:
    from lxml import etree

    src = etree.fromstring(payload.encode("utf-8"))
    xslt = etree.XSLT(etree.fromstring(stylesheet.encode("utf-8")))
    result = xslt(src)
    return {"transformed": str(result)}
