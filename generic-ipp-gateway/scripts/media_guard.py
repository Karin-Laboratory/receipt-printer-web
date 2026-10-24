"""Strict original IPP media admission before PAPPL normalizes attributes.

This parser only covers the IPP attribute section. Trailing binary document
data is deliberately opaque. Unsupported/malformed job media fails closed.
"""
from dataclasses import dataclass

ALLOWED_MEDIA = b"custom_receipt_80x200mm"
MAX_ATTRIBUTES = 512
MAX_ATTRIBUTE_BYTES = 65536


class IPPFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Attribute:
    name: str
    tag: int
    data: bytes
    group: int


def parse_ipp(payload: bytes):
    if len(payload) < 9 or payload[0] not in (1, 2):
        raise IPPFormatError("invalid IPP version/header")
    pos, group, last_name, attrs = 8, 0, "", []
    while pos < len(payload) and pos <= MAX_ATTRIBUTE_BYTES:
        tag = payload[pos]
        pos += 1
        if tag == 3:
            return (int.from_bytes(payload[2:4], "big"), attrs, pos)
        if tag <= 0x0f:
            if tag not in (1, 2, 4, 5, 6, 7, 8, 9):
                raise IPPFormatError("unknown group delimiter")
            group, last_name = tag, ""
            continue
        if not group or pos + 4 > len(payload):
            raise IPPFormatError("attribute outside group or truncated header")
        nlen = int.from_bytes(payload[pos:pos + 2], "big")
        pos += 2
        if nlen > 255 or pos + nlen + 2 > len(payload):
            raise IPPFormatError("invalid attribute name length")
        name_bytes = payload[pos:pos + nlen]
        pos += nlen
        vlen = int.from_bytes(payload[pos:pos + 2], "big")
        pos += 2
        if pos + vlen > len(payload):
            raise IPPFormatError("truncated attribute value")
        val = payload[pos:pos + vlen]
        pos += vlen
        if nlen:
            try:
                last_name = name_bytes.decode("ascii")
            except UnicodeDecodeError as exc:
                raise IPPFormatError("non-ASCII attribute name") from exc
        elif not last_name:
            raise IPPFormatError("repeated attribute with no name")
        attrs.append(Attribute(last_name, tag, val, group))
        if len(attrs) > MAX_ATTRIBUTES:
            raise IPPFormatError("too many attributes")
    raise IPPFormatError("attribute section exceeds limit or no end tag")


def decode_attributes(payload: bytes, *, limit: int = MAX_ATTRIBUTE_BYTES):
    if len(payload) > limit:
        raise IPPFormatError("attribute data too long")
    return parse_ipp(payload)[1]


def _check_collection(attrs: list[Attribute], start: int):
    # beginCollection, memberAttrName, typed value, endCollection are IPP tags
    stack = []
    pending = None
    dimensions = {}
    name = None
    i = start
    while i < len(attrs):
        a = attrs[i]
        if a.tag == 0x34:
            if a.data or (not stack and a.name != "media-col"):
                return False, i
            if stack and pending not in ("media-size",):
                return False, i
            stack.append("media-col" if not stack else pending)
            pending = None
        elif a.tag == 0x37:
            if a.data or not stack:
                return False, i
            stack.pop()
            if not stack:
                good_size = dimensions.get("x-dimension") == 8000 and dimensions.get("y-dimension", 0) > 0
                good_name = name == ALLOWED_MEDIA
                return (good_size or good_name) and (name is None or name == ALLOWED_MEDIA), i
            pending = None
        elif a.tag == 0x4a:
            if not stack or not a.data:
                return False, i
            try:
                pending = a.data.decode("ascii")
            except UnicodeDecodeError:
                return False, i
        elif stack:
            if pending == "media-size-name":
                if a.tag not in (0x44, 0x42) or name is not None:
                    return False, i
                name = a.data
            elif pending in ("x-dimension", "y-dimension"):
                if stack[-1] != "media-size" or a.tag != 0x21 or len(a.data) != 4 or pending in dimensions:
                    return False, i
                dimensions[pending] = int.from_bytes(a.data, "big", signed=True)
            elif pending in ("media-source", "media-type"):
                if a.tag not in (0x44, 0x42):
                    return False, i
            else:
                return False, i
            pending = None
        else:
            return False, i
        i += 1
    return False, i


def admit_job_media(attrs: list[Attribute]):
    job = [a for a in attrs if a.group == 2]
    media = [a for a in job if a.name == "media" and a.tag not in (0x4a, 0x34, 0x37)]
    if len(media) > 1:
        return False
    if media and (media[0].tag not in (0x42, 0x44) or media[0].data != ALLOWED_MEDIA):
        return False
    starts = [i for i, a in enumerate(job) if a.name == "media-col" and a.tag == 0x34]
    if starts:
        good, end = _check_collection(job, starts[0])
        if not good:
            return False
        # Prevent media collection attributes after its closure.
        if any(a.name == "media-col" for a in job[end + 1:]):
            return False
    elif any(a.name == "media-col" for a in job):
        return False
    # No explicit media => 80mm queue default, not an implicit A4 request.
    return True


def admit_80mm(payload: bytes):
    operation, attrs, _ = parse_ipp(payload)
    if operation not in (0x0002, 0x0004, 0x0005):
        return False
    return admit_job_media(attrs)
