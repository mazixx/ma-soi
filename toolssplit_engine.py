from pathlib import Path
import ast
import sys


# Các hàm chỉ phục vụ giao diện Tkinter.
UI_FUNCTIONS = {
    "v4_send_chat",
    "v5_show_summary",
    "v8_menu",
    "v8_start",
    "v11_show_reports",
    "v12_send_chat",
    "v12_refresh_info",
}


BRIDGE = r'''

# ============================================================
# GIAO TIẾP VỚI GIAO DIỆN KIVY
# ============================================================

def v5_show_summary(app, text):
    app.show_summary(text)


def v11_show_reports(app, detail, review):
    app.show_reports(detail, review)


def create_game(
    app,
    counts,
    moderator=True,
    human_name="Bạn",
    reveal=True,
    discussion=60,
    defense=30,
    vote=30,
    basic=False,
):
    global DAY_TIME, DEFENSE_TIME, VOTE_TIME

    if not isinstance(counts, dict):
        raise ValueError("Đội hình phải là một đối tượng JSON.")

    if set(counts) - set(ROLE):
        unknown = sorted(set(counts) - set(ROLE))
        raise ValueError("Mã vai không hợp lệ: " + ", ".join(unknown))

    normalized = {}

    for role in ROLE:
        count = counts.get(role, 0)

        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError("Số lượng mỗi vai phải là số nguyên.")

        if count < 0:
            raise ValueError("Số lượng vai không được âm.")

        if role not in ("V", "W") and count > 1:
            raise ValueError("Mỗi vai đặc biệt tối đa một bản sao.")

        if basic and role not in BASIC and count:
            raise ValueError(
                "Bộ cơ bản không hỗ trợ vai: " + ROLE[role]
            )

        normalized[role] = count

    total = sum(normalized.values())
    wolves = normalized["W"] + normalized["D"]

    if not 5 <= total <= 30:
        raise ValueError("Cần từ 5 đến 30 người.")

    if wolves < 1 or wolves >= total - wolves:
        raise ValueError(
            "Cần ít nhất một Sói; số Sói phải ít hơn số người còn lại."
        )

    for value, minimum, maximum, title in (
        (discussion, 10, 600, "Thảo luận"),
        (defense, 10, 600, "Biện hộ"),
        (vote, 5, 300, "Bỏ phiếu"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(title + ": phải nhập số nguyên.")

        if not minimum <= value <= maximum:
            raise ValueError(
                f"{title}: cần từ {minimum} đến {maximum} giây."
            )

    DAY_TIME = discussion
    DEFENSE_TIME = defense
    VOTE_TIME = vote

    roles = [
        role
        for role, count in normalized.items()
        for _ in range(count)
    ]

    return Game(
        app,
        roles,
        moderator,
        human_name.strip()[:18] or "Bạn",
        reveal,
    )


def role_visible(g, person):
    return (
        g.gm
        or g.done
        or person.id == g.human
        or person.revealed
    )


def player_information(g, person):
    """Không đưa thông tin kín của người khác ra giao diện."""
    full = g.gm or g.done or person.id == g.human
    info = []

    if person.no_vote:
        info.append("Mất phiếu")

    if not full:
        return " · ".join(info)

    if person.lover is not None:
        info.append(f"Yêu #{person.lover}")

    if person.model is not None:
        info.append(f"Hình mẫu #{person.model}")

    if person.enchanted:
        info.append("Bị mê hoặc")

    if person.role == "G" and person.last_guard is not None:
        info.append(f"Bảo vệ trước: #{person.last_guard}")

    if person.role == "F":
        info.append(
            f"Cứu: {int(person.heal)} | Độc: {int(person.poison)}"
        )

    if person.seen:
        info.append(
            "Soi: " + ", ".join(
                f"#{i}: {'Sói' if result else 'không Sói'}"
                for i, result in person.seen.items()
            )
        )

    if person.original != person.role:
        info.append("Vai gốc: " + ROLE[person.original])

    return " · ".join(info)


def visible_roster(g):
    rows = []

    for person in g.people.values():
        role = ROLE[person.role] if role_visible(g, person) else "?"

        if (
            not role_visible(g, person)
            and g.human is not None
            and person.id in g.p(g.human).pack
        ):
            role = "Đồng đội Sói"

        rows.append({
            "id": person.id,
            "name": person.name,
            "role": role,
            "alive": person.alive,
            "information": player_information(g, person),
        })

    return rows
'''


def uses_app_class(node):
    return any(
        isinstance(child, ast.Name) and child.id == "App"
        for child in ast.walk(node)
    )


def main():
    source = Path(
        sys.argv[1] if len(sys.argv) > 1 else "ma_soi_original.py"
    )

    if not source.exists():
        raise SystemExit(f"Không tìm thấy: {source}")

    tree = ast.parse(
        source.read_text(encoding="utf-8-sig"),
        filename=str(source),
    )

    kept = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            aliases = [
                alias
                for alias in node.names
                if not alias.name.startswith("tkinter")
            ]

            if aliases:
                node.names = aliases
                kept.append(node)

        elif isinstance(node, ast.ImportFrom):
            if not (node.module or "").startswith("tkinter"):
                kept.append(node)

        elif isinstance(node, ast.ClassDef):
            if node.name in {"Person", "Game"}:
                kept.append(node)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in UI_FUNCTIONS:
                kept.append(node)

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Loại App.menu = ..., _OLD = App.xxx...
            if not uses_app_class(node):
                kept.append(node)

        # Không giữ khối khởi động Tkinter:
        # if __name__ == "__main__": ...

    output_tree = ast.Module(body=kept, type_ignores=[])
    ast.fix_missing_locations(output_tree)

    result = ast.unparse(output_tree) + "\n" + BRIDGE

    # Kiểm tra cú pháp trước khi ghi.
    compile(result, "engine.py", "exec")

    destination = Path("engine.py")
    destination.write_text(result, encoding="utf-8")

    print(f"Đã tạo: {destination.resolve()}")
    print("Đã loại Tkinter và các bản vá giao diện App.")
    print("Đã giữ luật chơi và các bản vá Game theo thứ tự gốc.")


if __name__ == "__main__":
    main()
