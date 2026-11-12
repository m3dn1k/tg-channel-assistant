import re


def parse_channel(raw: str) -> int | str:
    raw = raw.strip()
    private = re.search(r"(?:https?://)?t\.me/c/(\d+)", raw, flags=re.IGNORECASE)
    if private:
        return int("-100" + private.group(1))
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    name = raw.rstrip("/").split("/")[-1]
    if name.startswith("@"):
        name = name[1:]
    return name


def message_link(chat_id: int, msg_id: int) -> str:
    raw = str(chat_id)
    if raw.startswith("-100"):
        raw = raw[4:]
    elif raw.startswith("-"):
        raw = raw[1:]
    return f"https://t.me/c/{raw}/{msg_id}"
