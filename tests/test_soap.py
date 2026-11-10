import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.soap import build_soap_envelope, extract_tag_value, parse_soap_fault, parse_soap_response

MOCKS_DIR = os.path.join(os.path.dirname(__file__), "mocks")

def test_build_soap_envelope_no_params():
    xml = build_soap_envelope("urn:dslforum-org:service:Hosts:1", "GetHostNumberOfEntries")
    assert "<u:GetHostNumberOfEntries xmlns:u=\"urn:dslforum-org:service:Hosts:1\">" in xml
    assert "</u:GetHostNumberOfEntries>" in xml

def test_build_soap_envelope_with_params():
    xml = build_soap_envelope(
        "urn:dslforum-org:service:Hosts:1",
        "GetGenericHostEntry",
        {"NewIndex": "5"}
    )
    assert "<NewIndex>5</NewIndex>" in xml
    assert "<u:GetGenericHostEntry xmlns:u=\"urn:dslforum-org:service:Hosts:1\">" in xml

def test_build_soap_envelope_escapes_values_and_rejects_tag_injection():
    xml = build_soap_envelope(
        "urn:test&service", "Action", {"NewName": "A&B <tablet>"}
    )
    assert 'xmlns:u="urn:test&amp;service"' in xml
    assert "<NewName>A&amp;B &lt;tablet&gt;</NewName>" in xml
    with pytest.raises(ValueError):
        build_soap_envelope("urn:test", "Bad<Action")
    with pytest.raises(ValueError):
        build_soap_envelope("urn:test", "Action", {"Bad<Tag": "value"})

def test_extract_tag_value_basic():
    xml = "<data><NewHostNumberOfEntries>42</NewHostNumberOfEntries></data>"
    val = extract_tag_value(xml, "NewHostNumberOfEntries")
    assert val == "42"

def test_extract_tag_value_with_attributes():
    xml = '<response><item id="123" type="host">Phone</item></response>'
    val = extract_tag_value(xml, "item")
    assert val == "Phone"

def test_extract_tag_value_not_found():
    xml = "<data><foo>bar</foo></data>"
    assert extract_tag_value(xml, "missing_tag") is None

def test_parse_soap_response_multiple_tags():
    with open(os.path.join(MOCKS_DIR, "hosts_entry_0.xml"), "r", encoding="utf-8") as f:
        xml = f.read()

    tags = ["NewIPAddress", "NewMACAddress", "NewHostName", "NewActive"]
    parsed = parse_soap_response(xml, tags)
    assert parsed["NewIPAddress"] == "192.168.178.20"
    assert parsed["NewMACAddress"] == "AA:BB:CC:DD:EE:01"
    assert parsed["NewHostName"] == "Kids-Tablet"
    assert parsed["NewActive"] == "1"

def test_parse_soap_fault():
    with open(os.path.join(MOCKS_DIR, "soap_fault_714.xml"), "r", encoding="utf-8") as f:
        xml = f.read()

    fault = parse_soap_fault(xml)
    assert fault is not None
    assert fault["error_code"] == 714
    assert fault["error_description"] == "NoSuchEntryInArray"
    assert fault["faultstring"] == "UPnPError"

def test_parse_soap_fault_on_valid_response():
    with open(os.path.join(MOCKS_DIR, "hosts_count.xml"), "r", encoding="utf-8") as f:
        xml = f.read()

    fault = parse_soap_fault(xml)
    assert fault is None

def test_parse_namespaced_fault_with_different_prefix():
    xml = (
        '<env:Envelope><env:Body><env:Fault><faultcode>env:Client</faultcode>'
        '<detail><upnp:errorCode>402</upnp:errorCode>'
        '<upnp:errorDescription>Invalid Args</upnp:errorDescription></detail>'
        '</env:Fault></env:Body></env:Envelope>'
    )
    fault = parse_soap_fault(xml)
    assert fault["error_code"] == 402
    assert fault["error_description"] == "Invalid Args"
