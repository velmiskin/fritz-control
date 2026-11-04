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

def build_soap_envelope(service_type, action_name, params=None):
    """
    Builds a compact SOAP 1.1 XML payload.
    :param service_type: URN string (e.g. 'urn:dslforum-org:service:Hosts:1')
    :param action_name: SOAP action string (e.g. 'GetHostNumberOfEntries')
    :param params: Optional dict of {param_name: value}
    :return: Formatted XML string
    """
    params_xml = ""
    if params:
        for k, v in params.items():
            params_xml += f"<{k}>{v}</{k}>"
    return SOAP_ENVELOPE_TEMPLATE.format(
        service=service_type,
        action=action_name,
        params=params_xml
    )

def extract_tag_value(xml_text, tag_name):
    """
    Extracts the inner text of an XML tag using zero-regex string slicing.
    Handles <tag>val</tag> and <tag attr="...">val</tag>.
    """
    if not xml_text or not tag_name:
        return None

    # Search for <tag>
    start_tag = f"<{tag_name}>"
    start = xml_text.find(start_tag)
    if start != -1:
        start_val = start + len(start_tag)
    else:
        # Search for <tag with attributes
        attr_tag = f"<{tag_name} "
        start = xml_text.find(attr_tag)
        if start == -1:
            return None
        close_bracket = xml_text.find(">", start)
        if close_bracket == -1:
            return None
        start_val = close_bracket + 1

    end_tag = f"</{tag_name}>"
    end_val = xml_text.find(end_tag, start_val)
    if end_val == -1:
        return None

    return xml_text[start_val:end_val].strip()

def parse_soap_fault(xml_text):
    """
    Checks if XML contains a SOAP Fault and extracts error details.
    :return: dict with fault details or None if not a fault
    """
    if "<s:Fault>" not in xml_text and "<Fault>" not in xml_text:
        return None

    faultcode = extract_tag_value(xml_text, "faultcode")
    faultstring = extract_tag_value(xml_text, "faultstring")
    error_code = extract_tag_value(xml_text, "errorCode")
    error_desc = extract_tag_value(xml_text, "errorDescription")

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
