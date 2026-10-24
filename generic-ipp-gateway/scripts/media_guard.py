"""Fail-closed IPP media admission before PAPPL normalizes media attributes.

Standalone capture-only preflight helper. Not yet wired into PAPPL/HTTP ingress.
"""
from dataclasses import dataclass


class IPPFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Attribute:
    name: str
    tag: int
    data: bytes
    group: int


def decode_attributes(payload: bytes, *, limit: int = 65536) -> list[Attribute]:
    """Decode IPP attributes without substituting unsupported media."""
    if len(payload) < 9 or len(payload) > limit or payload[0] not in (1, 2):
        raise IPPFormatError("invalid IPP header or size")
    attrs = []
    pos, group, last_name, depth = 8, 0, "", 0
    while pos < len(payload):
        tag = payload[pos]
        pos += 1
        if tag == 3:
            if depth:
                raise IPPFormatError("unclosed collection")
            return attrs
        if tag <= 0x0f:
            if tag not in (1, 2, 4, 5, 6, 7, 8, 9) or depth:
                raise IPPFormatError("invalid group delimiter")
            group, last_name = tag, ""
            continue
        if not group or pos + 4 > len(payload):
            raise IPPFormatError("attribute without group")
        name_len = int.from_bytes(payload[pos:pos+2], "big")
        pos += 2
        if pos + name_len + 2 > len(payload):
            raise IPPFormatError("truncated name")
        name_bytes = payload[pos:pos+name_len]
        pos += name_len
        value_len = int.from_bytes(payload[pos:pos+2], "big")
        pos += 2
        if pos + value_len > len(payload):
            raise IPPFormatError("truncated value")
        value = payload[pos:pos+value_len]
        pos += value_len
        if name_len:
            try:
                last_name = name_bytes.decode("ascii")
            except UnicodeDecodeError as exc:
                raise IPPFormatError("invalid attribute name") from exc
        elif not last_name:
            raise IPPFormatError("missing repeated name")
        if tag == 0x34:
            depth += 1
            if depth > 5:
                raise IPPFormatError("collection nesting limit")
        elif tag == 0x37:
            if not depth:
                raise IPPFormatError("unexpected endCollection")
            depth -= 1
        attrs.append(Attribute(last_name, tag, value, group))
        if len(attrs) > 512:
            raise IPPFormatError("too many attributes")
    raise IPPFormatError("missing end-of-attributes")


def admit_80mm(payload: bytes) -> bool:
    """Conservative first-stage policy; media-col is refused pending support."""
    job = [a for a in decode_attributes(payload) if a.group == 2]
    media = [a for a in job if a.name == "media"]
    if len(media) != 1 or any(a.name == "media-col" for a in job):
        return False
    return media[0].tag in (0x42, 0x44) and media[0].data == b"custom_receipt_80x200mm"
