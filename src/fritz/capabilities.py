"""Small SCPD capability parser for optional TR-064 actions."""

from fritz.soap import extract_tag_value, extract_tag_values


def parse_action_names(scpd_xml):
    action_list = extract_tag_value(scpd_xml, "actionList")
    if action_list is None:
        raise ValueError("SCPD actionList is missing")
    actions = []
    for action_xml in extract_tag_values(action_list, "action"):
        name = extract_tag_value(action_xml, "name")
        if name and name not in actions:
            actions.append(name)
    return tuple(actions)


class ServiceCapabilities:
    def __init__(self, service_type, scpd_url, actions):
        self.service_type = service_type
        self.scpd_url = scpd_url
        self.actions = tuple(actions)

    def supports(self, action_name):
        return action_name in self.actions

    @classmethod
    async def discover(cls, client, service_type, scpd_url):
        scpd_xml = await client.get_document(scpd_url)
        return cls(service_type, scpd_url, parse_action_names(scpd_xml))
