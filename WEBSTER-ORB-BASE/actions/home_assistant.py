"""G5.60: explicit Home Assistant REST call to a pre-allowlisted entity."""
ACTION_ID = "home_assistant"
DESCRIPTION = "Call a configured Home Assistant service for an entity explicitly listed in .env."

def run():
    import os
    import json
    import urllib.request
    from urllib.parse import urlparse
    base = os.getenv("HOME_ASSISTANT_URL", "").strip().rstrip("/")
    token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
    allowed = {item.strip() for item in os.getenv("HOME_ASSISTANT_ALLOWED_ENTITIES", "").split(",") if item.strip()}
    if not base or not token or not allowed:
        return "Configure HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN and HOME_ASSISTANT_ALLOWED_ENTITIES in your local .env file."
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "HOME_ASSISTANT_URL must be a valid http(s) URL."
    parts = [p.strip() for p in ACTION_ARGUMENTS.split("|")]
    if len(parts) != 2:
        return "Supply service and entity_id separated by |, e.g. light.turn_on | light.study."
    service, entity = parts
    if entity not in allowed:
        return "That entity is not in HOME_ASSISTANT_ALLOWED_ENTITIES; request denied."
    if service not in {"light.turn_on", "light.turn_off", "switch.turn_on", "switch.turn_off"}:
        return "Allowed services: light.turn_on/off and switch.turn_on/off."
    domain, action = service.split(".")
    if not entity.startswith(domain + "."):
        return "Service domain does not match the entity type."
    payload = json.dumps({"entity_id": entity}).encode("utf-8")
    request = urllib.request.Request(base + "/api/services/" + domain + "/" + action, data=payload, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status not in (200, 201):
                return f"Home Assistant returned HTTP {response.status}."
        return f"Home Assistant accepted {service} for {entity}."
    except Exception as exc:
        return f"Home Assistant request failed: {exc}"
