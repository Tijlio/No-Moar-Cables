import json
from urllib.parse import quote
from urllib.request import Request, urlopen


def launch_bravia_web_url(tv_ip, url, passcode, timeout=10):
    if not tv_ip:
        raise ValueError("TV IP is required.")

    if not passcode:
        raise ValueError("Sony BRAVIA pre-shared key is required.")

    app_uri = "localapp://webappruntime?url=" + quote(url, safe="")
    body = json.dumps(
        {
            "method": "setActiveApp",
            "id": 601,
            "params": [{"uri": app_uri}],
            "version": "1.0",
        }
    ).encode("utf-8")

    request = Request(
        f"http://{tv_ip}/sony/appControl",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Auth-PSK": passcode,
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")

    if not payload:
        return {}

    data = json.loads(payload)
    if "error" in data:
        raise RuntimeError(f"BRAVIA API error: {data['error']}")

    return data
