import json
import math
from datetime import datetime

import engine as rules


ROOM = None
ROOM_SERIAL = 0


class WebView:
    def __init__(self):
        self.events = []
        self.action = None
        self.action_serial = 0

    def append(self, text, chat=False):
        public_event = (
            "[KÍN]" not in text
            and any(marker in text for marker in (
                "────",
                "đã chết",
                "THẮNG",
                "HÒA",
                "Hết giờ",
                "không có ai chết",
                "Quyết định treo",
                "Hòa phiếu",
                "Gấu ",
                "gấu ",
                "phiếu cho",
                "phiếu trắng",
            ))
        )

        report = (
            "[BÁO CÁO CHI TIẾT CUỐI VÁN]" in text
            or "[ĐÁNH GIÁ CUỐI VÁN]" in text
        )

        self.events.append({
            "type": "message",
            "text": text,
            "chat": bool(chat or (public_event and not report)),
        })

    def show_action(self, title, options, minimum, maximum, optional):
        self.action_serial += 1

        self.action = {
            "id": self.action_serial,
            "title": title,
            "options": list(options),
            "minimum": minimum,
            "maximum": maximum,
            "optional": optional,
            "submitted": False,
        }

    def clear_action(self):
        self.action = None

    def show_summary(self, text):
        self.events.append({
            "type": "summary",
            "text": text,
        })

    def show_reports(self, detail, review):
        self.events.append({
            "type": "reports",
            "detail": detail,
            "review": review,
        })

    def drain(self):
        events = self.events
        self.events = []
        return events


def integer(value, minimum, maximum, label):
    if type(value) is not int:
        raise ValueError(f"{label}: cần nhập số nguyên.")

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{label}: cần từ {minimum} đến {maximum}."
        )

    return value


def visible_role(game, person):
    return (
        game.gm
        or game.done
        or person.id == game.human
        or person.revealed
    )


def extra_info(game, person):
    full = game.gm or game.done or person.id == game.human
    info = []

    if person.no_vote:
        info.append("Mất phiếu")

    if full:
        if person.lover is not None:
            info.append(f"Người yêu #{person.lover}")

        if person.model is not None:
            info.append(f"Hình mẫu #{person.model}")

        if person.enchanted:
            info.append("Bị mê hoặc")

        if person.role == "G" and person.last_guard is not None:
            info.append(f"Bảo vệ trước #{person.last_guard}")

        if person.role == "F":
            info.append(
                f"Cứu: {int(person.heal)} • Độc: {int(person.poison)}"
            )

        if person.seen:
            info.append(
                "Soi: " + ", ".join(
                    f"#{pid}: {'Sói' if result else 'không Sói'}"
                    for pid, result in person.seen.items()
                )
            )

        if person.original != person.role:
            info.append("Vai gốc: " + rules.ROLE[person.original])

    return " • ".join(info)


def roster(game):
    rows = []

    for person in game.people.values():
        role = (
            rules.ROLE[person.role]
            if visible_role(game, person)
            else "Vai bí mật"
        )

        if (
            not visible_role(game, person)
            and game.human is not None
            and person.id in game.p(game.human).pack
        ):
            role = "Đồng đội Sói"

        rows.append({
            "id": person.id,
            "name": person.name,
            "role": role,
            "alive": person.alive,
            "self": person.id == game.human,
            "information": extra_info(game, person),
        })

    return rows


class Room:
    def __init__(self, settings):
        global ROOM_SERIAL

        mode = settings.get("mode", "Cơ bản")
        size = str(settings.get("size", "10"))

        if mode not in rules.PRESET:
            raise ValueError("Bộ luật không hợp lệ.")

        if size == "custom":
            counts = settings.get("counts", {})
        else:
            try:
                counts = rules.PRESET[mode][int(size)]
            except (ValueError, KeyError):
                raise ValueError("Số người không hợp lệ.")

        if not isinstance(counts, dict):
            raise ValueError("Đội hình không hợp lệ.")

        unknown = set(counts) - set(rules.ROLE)

        if unknown:
            raise ValueError("Mã vai không hợp lệ.")

        normalized = {}

        for role in rules.ROLE:
            count = integer(
                counts.get(role, 0),
                0,
                30 if role in ("V", "W") else 1,
                rules.ROLE[role],
            )

            if mode == "Cơ bản" and role not in rules.BASIC and count:
                raise ValueError("Vai này không thuộc bộ cơ bản.")

            normalized[role] = count

        total = sum(normalized.values())
        wolves = normalized["W"] + normalized["D"]

        if not 5 <= total <= 30:
            raise ValueError("Cần từ 5 đến 30 người.")

        if wolves < 1 or wolves >= total - wolves:
            raise ValueError(
                "Cần ít nhất một Sói; số Sói phải ít hơn người còn lại."
            )

        discussion = integer(
            settings.get("discussion", 60), 10, 600, "Thảo luận"
        )

        defense = integer(
            settings.get("defense", 30), 10, 600, "Biện hộ"
        )

        vote = integer(
            settings.get("vote", 30), 5, 300, "Bỏ phiếu"
        )

        rules.DAY_TIME = discussion
        rules.DEFENSE_TIME = defense
        rules.VOTE_TIME = vote

        roles = [
            role
            for role, count in normalized.items()
            for _ in range(count)
        ]

        ROOM_SERIAL += 1
        self.id = ROOM_SERIAL
        self.view = WebView()

        self.game = rules.Game(
            self.view,
            roles,
            bool(settings.get("moderator", True)),
            str(settings.get("name", "Bạn")).strip()[:18] or "Bạn",
            bool(settings.get("reveal", True)),
        )

    def snapshot(self):
        game = self.game

        remaining = None

        if game.deadline is not None:
            remaining = max(
                0, math.ceil(game.deadline - game.clock)
            )

        if game.gm:
            wolves = sum(game.p(pid).wolf for pid in game.live())

            private = (
                f"QUẢN TRÒ • Sói còn sống: {wolves}\n"
                "Bạn được xem vai và hành động kín."
            )
        else:
            person = game.p(game.human)

            state = (
                "Còn sống"
                if person.alive
                else "Đã chết — được chat hồn ma"
            )

            private = (
                f"#{person.id} {person.name} • "
                f"{rules.ROLE[person.role]} • {state}\n"
                f"{rules.DESC[person.role]}\n"
                f"{extra_info(game, person)}"
            )

        return {
            "room": self.id,
            "day": game.day,
            "phase": game.phase,
            "clock": round(game.clock, 2),
            "remaining": remaining,
            "paused": game.paused,
            "done": game.done,
            "moderator": game.gm,
            "human": game.human,
            "alive": len(game.live()),
            "total": len(game.people),
            "light": game.light,
            "private": private,
            "players": roster(game),
            "action": self.view.action,
            "banner": (
                game.banner
                if game.clock < game.banner_until
                else ""
            ),
        }

    def submit(self, token, selected):
        game = self.game
        action = self.view.action

        if game.paused or game.done:
            raise ValueError("Ván đang dừng hoặc đã kết thúc.")

        if not action or action["id"] != token:
            raise ValueError("Hành động đã hết hiệu lực.")

        if action["submitted"]:
            raise ValueError("Bạn đã gửi hành động này.")

        if not isinstance(selected, list):
            raise ValueError("Lựa chọn không hợp lệ.")

        if any(type(item) not in (int, str) for item in selected):
            raise ValueError("Lựa chọn không hợp lệ.")

        if len(selected) != len(set(selected)):
            raise ValueError("Không được chọn trùng.")

        allowed = {key for key, _ in action["options"]}

        if any(item not in allowed for item in selected):
            raise ValueError("Mục tiêu không hợp lệ.")

        skip = not selected and action["optional"]

        if not skip and not (
            action["minimum"] <= len(selected) <= action["maximum"]
        ):
            raise ValueError(
                f"Cần chọn {action['minimum']}–"
                f"{action['maximum']} mục."
            )

        game.answer = list(selected)
        action["submitted"] = True

    def export(self, notes):
        game = self.game

        data = {
            "exported_at": datetime.now().isoformat(),
            "mode": "moderator" if game.gm else "player",
            "day": game.day,
            "phase": game.phase,
            "finished": game.done,
            "notes": str(notes),
            "players": roster(game),
            "ballots": game.ballots,
            "history": [
                item for item in game.history
                if game.visible(item["scope"])
            ],
        }

        return {
            "filename": (
                f"ma_soi_{datetime.now():%Y%m%d_%H%M%S}.json"
            ),
            "data": data,
        }


def api(raw):
    global ROOM

    request = json.loads(raw)
    operation = request.get("op")

    if operation == "meta":
        return json.dumps({
            "meta": {
                "roles": rules.ROLE,
                "descriptions": rules.DESC,
                "basic": sorted(rules.BASIC),
                "presets": rules.PRESET,
            },
            "state": None,
            "events": [],
        }, ensure_ascii=False)

    download = None

    if operation == "new":
        ROOM = Room(request.get("settings", {}))

    else:
        if ROOM is None:
            raise ValueError("Hãy bắt đầu ván trước.")

        game = ROOM.game

        if operation == "tick":
            dt = max(0.0, min(float(request.get("dt", 0.1)), 0.25))

            try:
                game.tick(dt)
            except Exception:
                game.paused = True
                raise

        elif operation == "action":
            ROOM.submit(
                request.get("token"),
                request.get("selected", []),
            )

        elif operation == "chat":
            if not game.human_chat(str(request.get("text", ""))):
                raise ValueError(
                    "Chưa thể gửi: kiểm tra pha chơi, quyền biện hộ, "
                    "tạm dừng hoặc chờ một chút."
                )

        elif operation == "pause":
            if not game.done:
                game.paused = bool(request.get("value", True))

        elif operation == "export":
            download = ROOM.export(request.get("notes", ""))

        else:
            raise ValueError("Lệnh không hợp lệ.")

    return json.dumps({
        "state": ROOM.snapshot(),
        "events": ROOM.view.drain(),
        "download": download,
    }, ensure_ascii=False)
