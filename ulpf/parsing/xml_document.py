"""XML decoding with a depth budget shared by document and event parsing."""

import io
import xml.etree.ElementTree as ET

MAX_XML_DEPTH = 256


def decode_xml(value: str) -> ET.Element:
    depth = 0
    parser = ET.iterparse(io.StringIO(value), events=("start", "end"))
    for event, _ in parser:
        if event == "start":
            depth += 1
            if depth > MAX_XML_DEPTH:
                raise ValueError(f"XML nesting exceeds the {MAX_XML_DEPTH}-element depth limit")
        else:
            depth -= 1
    return parser.root
