"""
src/fritz/soap.py - Ultra-lightweight SOAP 1.1 Envelope Builder & Fast String Parser
Designed specifically for MicroPython on ESP32 to eliminate XML DOM allocations.
"""

SOAP_ENVELOPE_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body>'
    '<u:{action} xmlns:u="{service}">'
    '{params}'
    '</u:{action}>'
    '</s:Body>'
    '</s:Envelope>'
)

_XML_NAME_START = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
_XML_NAME_CHARS = _XML_NAME_START + "0123456789.-"

def _is_xml_name(value):
    if not isinstance(value, str) or not value:
        return False
    if value[0] not in _XML_NAME_START:
        return False
    for char in value[1:]:
        if char not in _XML_NAME_CHARS:
            return False
    return True

def escape_xml_text(value):
    """Escapes a value for use as XML element text."""
    value = str(value)
    return (value.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))

def escape_xml_attribute(value):
    """Escapes a value for use in a double-quoted XML attribute."""
    return (escape_xml_text(value)
            .replace('"', "&quot;")
            .replace("'", "&apos;"))

def _unescape_xml_text(value):
    return (value.replace("&lt;", "<")
                 .replace("&gt;", ">")
                 .replace("&quot;", '"')
                 .replace("&apos;", "'")
                 .replace("&amp;", "&"))

def build_soap_envelope(service_type, action_name, params=None):
    """
    Builds a compact SOAP 1.1 XML payload.
    :param service_type: URN string (e.g. 'urn:dslforum-org:service:Hosts:1')
    :param action_name: SOAP action string (e.g. 'GetHostNumberOfEntries')
    :param params: Optional dict of {param_name: value}
    :return: Formatted XML string
    """
    if not _is_xml_name(action_name):
        raise ValueError("Invalid SOAP action name")

    param_parts = []
    if params:
        for k, v in params.items():
            if not _is_xml_name(k):
                raise ValueError("Invalid SOAP parameter name")
            param_parts.append("<{}>{}</{}>".format(k, escape_xml_text(v), k))
    return SOAP_ENVELOPE_TEMPLATE.format(
        service=escape_xml_attribute(service_type),
        action=action_name,
        params="".join(param_parts)
    )

def _find_element(xml_text, tag_name, start_pos=0):
    """Returns (inner_text, end_position) for a local-name XML tag."""
    pos = start_pos
    text_len = len(xml_text)
    while pos < text_len:
        start = xml_text.find("<", pos)
        if start == -1:
            return None
        if start + 1 >= text_len or xml_text[start + 1] in "/!?":
            pos = start + 1
            continue

        name_end = start + 1
        while name_end < text_len and xml_text[name_end] not in " \t\r\n/>":
            name_end += 1
        qualified_name = xml_text[start + 1:name_end]
        local_name = qualified_name.split(":")[-1]
        if local_name != tag_name:
            pos = name_end
            continue

        open_end = xml_text.find(">", name_end)
        if open_end == -1:
            return None
        if open_end > start and xml_text[open_end - 1] == "/":
            return "", open_end + 1

        close_tag = "</{}>".format(qualified_name)
        close_start = xml_text.find(close_tag, open_end + 1)
        if close_start == -1:
            return None
        return xml_text[open_end + 1:close_start], close_start + len(close_tag)
    return None

def extract_tag_value(xml_text, tag_name):
    """
    Extracts the inner text of an XML tag using zero-regex string slicing.
    Handles <tag>val</tag> and <tag attr="...">val</tag>.
    """
    if not xml_text or not tag_name:
        return None

    found = _find_element(xml_text, tag_name)
    if found is None:
        return None
    return _unescape_xml_text(found[0].strip())

def extract_tag_values(xml_text, tag_name):
    """Returns all values for a local-name XML tag without building a DOM."""
    values = []
    pos = 0
    while True:
        found = _find_element(xml_text, tag_name, pos)
        if found is None:
            return values
        values.append(_unescape_xml_text(found[0].strip()))
        pos = found[1]

def parse_soap_fault(xml_text):
    """
    Checks if XML contains a SOAP Fault and extracts error details.
    :return: dict with fault details or None if not a fault
    """
    fault_element = _find_element(xml_text, "Fault")
    if fault_element is None:
        return None

    fault_xml = fault_element[0]

    faultcode = extract_tag_value(fault_xml, "faultcode")
    faultstring = extract_tag_value(fault_xml, "faultstring")
    error_code = extract_tag_value(fault_xml, "errorCode")
    error_desc = extract_tag_value(fault_xml, "errorDescription")

    return {
        "faultcode": faultcode,
        "faultstring": faultstring,
        "error_code": int(error_code) if error_code and error_code.isdigit() else error_code,
        "error_description": error_desc or faultstring or "Unknown SOAP Fault"
    }

def parse_soap_response(xml_text, tags):
    """
    Extracts specified tags from a SOAP response string.
    :param xml_text: SOAP response XML string
    :param tags: list or tuple of tag names to extract
    :return: dict of {tag_name: extracted_value}
    """
    result = {}
    for tag in tags:
        val = extract_tag_value(xml_text, tag)
        result[tag] = val
    return result
