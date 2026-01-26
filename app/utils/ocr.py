import xml.etree.ElementTree as ET

async def parse_alarm_xml(xml_text: str):
    ns = {"h": "http://www.hikvision.com/ver20/XMLSchema"}
    root = ET.fromstring(xml_text)

    data = {
        "ip": root.findtext("h:ipAddress", namespaces=ns),
        "channel": root.findtext("h:channelID", namespaces=ns),
        "time": root.findtext("h:dateTime", namespaces=ns),
        "event": root.findtext("h:eventType", namespaces=ns),
        "state": root.findtext("h:eventState", namespaces=ns),
        "target": root.findtext("h:targetType", namespaces=ns),
        # "camName": root.findtext("h:channelName", namespaces=ns),
        "x": root.findtext(".//h:X", namespaces=ns),
        "y": root.findtext(".//h:Y", namespaces=ns),
        "w": root.findtext(".//h:width", namespaces=ns),
        "h": root.findtext(".//h:height", namespaces=ns),
    }
    return data