import ast
import copy
from pathlib import Path


SOURCE = Path("ma_soi_original.txt")
OUTPUT = Path("engine.py")

UI_FUNCTIONS = {
    "v4_send_chat",
    "v5_show_summary",
    "v8_menu",
    "v8_start",
    "v11_show_reports",
    "v12_send_chat",
    "v12_refresh_info",
}

BRIDGE = """
def v5_show_summary(app, text):
    app.show_summary(text)


def v11_show_reports(app, detail, review):
    app.show_reports(detail, review)
"""


def references_app(node):
    return any(
        isinstance(child, ast.Name) and child.id == "App"
        for child in ast.walk(node)
    )


def main():
    if not SOURCE.is_file():
        raise SystemExit("Thiếu file ma_soi_original.txt.")

    source = SOURCE.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(SOURCE))

    kept = []
    found_classes = set()

    for original in tree.body:
        node = copy.deepcopy(original)

        if isinstance(node, ast.Import):
            node.names = [
                alias
                for alias in node.names
                if not alias.name.startswith("tkinter")
            ]

            if node.names:
                kept.append(node)

        elif isinstance(node, ast.ImportFrom):
            if not (node.module or "").startswith("tkinter"):
                kept.append(node)

        elif isinstance(node, ast.ClassDef):
            if node.name in {"Person", "Game"}:
                kept.append(node)
                found_classes.add(node.name)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in UI_FUNCTIONS:
                kept.append(node)

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Loại App.send_chat = ... và _OLD = App.xxx.
            # Giữ các bản vá Game.xxx = ...
            if not references_app(node):
                kept.append(node)

        # Không giữ khối khởi động Tkinter hoặc lời gọi cấp module.

    if found_classes != {"Person", "Game"}:
        raise SystemExit(
            "File nguồn không đúng cấu trúc Ma Sói: thiếu Person/Game."
        )

    kept.extend(ast.parse(BRIDGE).body)

    output_tree = ast.Module(body=kept, type_ignores=[])
    ast.fix_missing_locations(output_tree)

    forbidden = {
        "tk", "ttk", "messagebox", "filedialog", "App"
    }

    references = {
        node.id
        for node in ast.walk(output_tree)
        if isinstance(node, ast.Name)
    }

    remaining = references & forbidden

    if remaining:
        raise SystemExit(
            "Engine còn phụ thuộc giao diện: "
            + ", ".join(sorted(remaining))
        )

    result = ast.unparse(output_tree) + "\n"

    compile(result, str(OUTPUT), "exec")
    OUTPUT.write_text(result, encoding="utf-8")

    print("Đã tạo engine.py.")
    print("Đã giữ luật chơi và các bản vá Game theo thứ tự nguồn.")
    print("Đã loại giao diện Tkinter.")


if __name__ == "__main__":
    main()
