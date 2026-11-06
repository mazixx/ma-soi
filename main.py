import json
import math
import traceback

from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from engine import (
    ROLE,
    DESC,
    PRESET,
    create_game,
    visible_roster,
    player_information,
)


class MaSoiApp(App):
    title = "Ma sói - Làng Sương Mù"

    def build(self):
        self.game = None
        self.refresh_elapsed = 0.0
        self.action_options = []
        self.choice_widgets = []

        self.settings = {
            "mode": "Cơ bản",
            "size": "10",
            "play": "Quản trò",
            "name": "Bạn",
            "reveal": "Có",
            "discussion": "60",
            "defense": "30",
            "vote": "30",
            "roles": '{"W": 2, "S": 1, "G": 1, "F": 1, "V": 5}',
        }

        self.container = BoxLayout(
            orientation="vertical",
            padding=dp(8),
            spacing=dp(6),
        )

        self.show_menu()
        Clock.schedule_interval(self.tick, 0.05)
        return self.container

    def notice(self, title, text):
        content = BoxLayout(
            orientation="vertical",
            padding=dp(8),
            spacing=dp(8),
        )

        content.add_widget(TextInput(text=text, readonly=True))

        close = Button(
            text="Đóng",
            size_hint_y=None,
            height=dp(44),
        )
        content.add_widget(close)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.9, 0.7),
        )
        close.bind(on_release=popup.dismiss)
        popup.open()

    def show_menu(self, *_):
        self.game = None
        self.container.clear_widgets()

        self.container.add_widget(Label(
            text="MA SÓI • LÀNG SƯƠNG MÙ",
            font_size="22sp",
            size_hint_y=None,
            height=dp(48),
        ))

        scroll = ScrollView()
        form = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))
        scroll.add_widget(form)
        self.container.add_widget(scroll)

        self.fields = {}

        def field(key, title, values=None):
            row = BoxLayout(
                size_hint_y=None,
                height=dp(46),
                spacing=dp(6),
            )

            row.add_widget(Label(text=title, size_hint_x=0.42))

            if values is not None:
                widget = Spinner(
                    text=self.settings[key],
                    values=values,
                )
            else:
                widget = TextInput(
                    text=self.settings[key],
                    multiline=False,
                )

            row.add_widget(widget)
            form.add_widget(row)
            self.fields[key] = widget

        field("mode", "Bộ luật", ("Cơ bản", "Nâng cao"))
        field("size", "Số người", ("5", "10", "15", "20", "Tùy chỉnh"))
        field("play", "Cách chơi", ("Quản trò", "Nhập vai"))
        field("name", "Tên của bạn")
        field("reveal", "Lộ vai khi chết", ("Có", "Không"))
        field("discussion", "Thảo luận: 10–600 giây")
        field("defense", "Biện hộ: 10–600 giây")
        field("vote", "Vote: 5–300 giây")
        field("roles", "Đội hình JSON tùy chỉnh")

        guide = TextInput(
            readonly=True,
            size_hint_y=None,
            height=dp(150),
            text=(
                "Đội hình JSON chỉ dùng khi chọn số người = Tùy chỉnh.\n"
                "Ví dụ: {\"W\": 1, \"S\": 1, \"V\": 3}\n\n"
                + " | ".join(f"{code}: {name}" for code, name in ROLE.items())
                + "\n\nChat hồn ma không ảnh hưởng suy luận của bot."
            ),
        )
        form.add_widget(guide)

        start = Button(
            text="BẮT ĐẦU VÁN",
            size_hint_y=None,
            height=dp(52),
        )
        start.bind(on_release=self.start_game)
        form.add_widget(start)

    def start_game(self, *_):
        values = {
            key: widget.text.strip()
            for key, widget in self.fields.items()
        }

        try:
            counts = (
                json.loads(values["roles"])
                if values["size"] == "Tùy chỉnh"
                else PRESET[values["mode"]][int(values["size"])]
            )

            # Game tạo generator nhưng chưa chạy ngay,
            # vì vậy có thể tạo trước khi dựng phòng.
            game = create_game(
                self,
                counts,
                moderator=values["play"] == "Quản trò",
                human_name=values["name"],
                reveal=values["reveal"] == "Có",
                discussion=int(values["discussion"]),
                defense=int(values["defense"]),
                vote=int(values["vote"]),
                basic=values["mode"] == "Cơ bản",
            )

        except (ValueError, TypeError, KeyError) as error:
            self.notice("Cấu hình không hợp lệ", str(error))
            return

        self.settings = values
        self.build_room()
        self.game = game
        self.refresh_elapsed = 0.0
        self.refresh_info()

    def make_tab(self, title, editable=False):
        tab = TabbedPanelItem(text=title)
        box = TextInput(
            readonly=not editable,
            multiline=True,
            font_size="14sp",
        )
        tab.add_widget(box)
        self.tabs.add_widget(tab)
        return tab, box

    def build_room(self):
        self.container.clear_widgets()

        top = BoxLayout(
            size_hint_y=None,
            height=dp(44),
            spacing=dp(5),
        )

        self.status_label = Label(text="Chuẩn bị...")
        top.add_widget(self.status_label)

        self.pause_button = Button(text="Tạm dừng", size_hint_x=0.3)
        self.pause_button.bind(on_release=self.pause)
        top.add_widget(self.pause_button)

        export_button = Button(text="Xuất", size_hint_x=0.2)
        export_button.bind(on_release=self.export)
        top.add_widget(export_button)

        leave_button = Button(text="Rời", size_hint_x=0.2)
        leave_button.bind(on_release=self.leave)
        top.add_widget(leave_button)

        self.container.add_widget(top)

        self.private_box = TextInput(
            readonly=True,
            size_hint_y=None,
            height=dp(72),
            font_size="13sp",
        )
        self.container.add_widget(self.private_box)

        body = BoxLayout(spacing=dp(7))
        self.container.add_widget(body)

        left = BoxLayout(
            orientation="vertical",
            size_hint_x=0.36,
            spacing=dp(5),
        )
        body.add_widget(left)

        self.action_label = Label(
            text="Đang theo dõi...",
            size_hint_y=None,
            height=dp(66),
        )
        self.action_label.bind(
            size=lambda widget, size: setattr(widget, "text_size", size)
        )
        left.add_widget(self.action_label)

        choices_scroll = ScrollView()
        self.choices_layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(4),
        )
        self.choices_layout.bind(
            minimum_height=self.choices_layout.setter("height")
        )
        choices_scroll.add_widget(self.choices_layout)
        left.add_widget(choices_scroll)

        action_buttons = BoxLayout(
            size_hint_y=None,
            height=dp(44),
            spacing=dp(4),
        )

        self.confirm_button = Button(text="Xác nhận")
        self.confirm_button.bind(on_release=self.confirm_action)

        self.skip_button = Button(text="Bỏ qua")
        self.skip_button.bind(on_release=self.skip_action)

        action_buttons.add_widget(self.confirm_button)
        action_buttons.add_widget(self.skip_button)
        left.add_widget(action_buttons)

        self.action_error = Label(
            text="",
            size_hint_y=None,
            height=dp(34),
        )
        self.action_error.bind(
            size=lambda widget, size: setattr(widget, "text_size", size)
        )
        left.add_widget(self.action_error)

        self.tabs = TabbedPanel(
            do_default_tab=False,
            tab_width=dp(108),
        )
        body.add_widget(self.tabs)

        self.chat_tab, self.chat_box = self.make_tab("Chat")
        _, self.history_box = self.make_tab("Lịch sử")
        _, self.notes_box = self.make_tab("Ghi chú", editable=True)
        _, self.roster_box = self.make_tab("Nhân vật")
        _, self.summary_box = self.make_tab("Tóm tắt")
        self.detail_tab, self.detail_box = self.make_tab("Chi tiết")
        self.review_tab, self.review_box = self.make_tab("Đánh giá")

        chat_row = BoxLayout(
            size_hint_y=None,
            height=dp(44),
            spacing=dp(5),
        )

        self.chat_input = TextInput(
            multiline=False,
            hint_text="Ví dụ: Mình nghi #3",
        )
        self.chat_input.bind(on_text_validate=self.send_chat)
        chat_row.add_widget(self.chat_input)

        send_button = Button(text="Gửi", size_hint_x=0.15)
        send_button.bind(on_release=self.send_chat)
        chat_row.add_widget(send_button)
        self.container.add_widget(chat_row)

        self.chat_hint = Label(
            text="Người sống chat ban ngày; người chết có chat hồn ma.",
            size_hint_y=None,
            height=dp(28),
            font_size="12sp",
        )
        self.container.add_widget(self.chat_hint)

        self.clear_action()

        # Đổi tab sau khi Kivy hoàn tất layout.
        Clock.schedule_once(
            lambda dt: self.tabs.switch_to(self.chat_tab), 0
        )

    @staticmethod
    def append_text(box, text):
        box.text += text + "\n"
        box.cursor = (0, len(box._lines) - 1)

    def append(self, text, chat=False):
        self.append_text(self.history_box, text)

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

        # Báo cáo dài đã có tab riêng và vẫn nằm trong lịch sử.
        report = (
            "[BÁO CÁO CHI TIẾT CUỐI VÁN]" in text
            or "[ĐÁNH GIÁ CUỐI VÁN]" in text
        )

        if chat or (public_event and not report):
            self.append_text(self.chat_box, text)

    def show_action(self, title, options, minimum, maximum, optional):
        self.action_options = list(options)
        self.action_min = minimum
        self.action_max = maximum
        self.action_optional = optional
        self.choice_widgets = []

        self.action_label.text = title
        self.action_error.text = ""
        self.choices_layout.clear_widgets()

        group = f"action-{id(options)}" if maximum == 1 else None

        for key, label in options:
            button = ToggleButton(
                text=label,
                group=group,
                size_hint_y=None,
                height=dp(44),
            )
            self.choice_widgets.append((key, button))
            self.choices_layout.add_widget(button)

        self.confirm_button.disabled = False
        self.skip_button.disabled = not optional

    def clear_action(self):
        self.action_options = []
        self.choice_widgets = []
        self.choices_layout.clear_widgets()
        self.action_label.text = "Đang theo dõi diễn biến..."
        self.action_error.text = ""
        self.confirm_button.disabled = True
        self.skip_button.disabled = True

    def submit_answer(self, selected):
        game = self.game

        if not game or game.paused or game.done:
            return

        game.answer = selected
        self.confirm_button.disabled = True
        self.skip_button.disabled = True

        for _, button in self.choice_widgets:
            button.disabled = True

        self.action_error.text = "Đã gửi."

    def confirm_action(self, *_):
        if self.confirm_button.disabled:
            return

        selected = [
            key
            for key, button in self.choice_widgets
            if button.state == "down"
        ]

        if not self.action_min <= len(selected) <= self.action_max:
            self.action_error.text = (
                f"Chọn {self.action_min}–{self.action_max} mục."
            )
            return

        self.submit_answer(selected)

    def skip_action(self, *_):
        if not self.skip_button.disabled:
            self.submit_answer([])

    def send_chat(self, *_):
        game = self.game

        if not game:
            return

        accepted = game.human_chat(self.chat_input.text)

        if accepted:
            self.chat_input.text = ""

            ghost = (
                game.human is not None
                and not game.p(game.human).alive
            )

            self.chat_hint.text = (
                "Chat hồn ma: không ảnh hưởng suy luận của bot."
                if ghost else "Đã gửi."
            )
        else:
            self.chat_hint.text = (
                "Chưa thể gửi: kiểm tra pha chơi, quyền biện hộ, "
                "tạm dừng hoặc chờ một chút."
            )

    def show_summary(self, text):
        self.summary_box.text = (
            text + "\n\n" + "═" * 35 + "\n\n" + self.summary_box.text
        )
        self.summary_box.cursor = (0, 0)

    def show_reports(self, detail, review):
        self.detail_box.text = detail
        self.review_box.text = review
        self.detail_box.cursor = (0, 0)
        self.review_box.cursor = (0, 0)
        self.tabs.switch_to(self.review_tab)

    def refresh_info(self):
        game = self.game

        if not game:
            return

        remaining = ""

        if game.deadline is not None:
            seconds = max(0, math.ceil(game.deadline - game.clock))
            remaining = f" | {seconds}s"

        self.status_label.text = (
            f"Ngày {game.day} | {game.phase}{remaining}"
            f" | {len(game.live())}/{len(game.people)}"
        )

        self.pause_button.text = (
            "Tiếp tục" if game.paused else "Tạm dừng"
        )

        if game.gm:
            wolves = sum(game.p(i).wolf for i in game.live())
            private = (
                f"QUẢN TRÒ | Sói còn sống: {wolves}\n"
                "Xem Nhân vật, Lịch sử và Tóm tắt để theo dõi."
            )
        else:
            person = game.p(game.human)
            state = (
                "Còn sống"
                if person.alive
                else "Đã chết — được chat hồn ma"
            )
            private = (
                f"#{person.id} {person.name} | {ROLE[person.role]} | {state}\n"
                f"{DESC[person.role]}\n"
                f"{player_information(game, person)}"
            )

        if self.private_box.text != private:
            self.private_box.text = private

        lines = []

        for row in visible_roster(game):
            state = "Sống" if row["alive"] else "Đã chết"
            lines.append(
                f"#{row['id']} {row['name']} | {row['role']} | {state}"
            )

            if row["information"]:
                lines.append("  " + row["information"])

        roster = "\n".join(lines)

        if self.roster_box.text != roster:
            self.roster_box.text = roster

    def pause(self, *_):
        if self.game and not self.game.done:
            self.game.paused = not self.game.paused
            self.refresh_info()

    def export(self, *_):
        game = self.game

        if not game:
            return

        folder = Path(self.user_data_dir) / "exports"
        filename = f"ma_soi_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
        path = folder / filename

        data = {
            "exported_at": datetime.now().isoformat(),
            "mode": "moderator" if game.gm else "player",
            "day": game.day,
            "phase": game.phase,
            "finished": game.done,
            "notes": self.notes_box.text,
            "players": visible_roster(game),
            "ballots": game.ballots,
            "history": [
                item
                for item in game.history
                if game.visible(item["scope"])
            ],
        }

        try:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            self.notice("Không lưu được", str(error))
            return

        self.notice(
            "Đã xuất nhật ký",
            f"Đã lưu tại:\n{path}\n\n"
            "Trên Android, đây là thư mục dữ liệu của ứng dụng, "
            "không phải thư mục Downloads.",
        )

    def leave(self, *_):
        game = self.game

        if not game:
            self.show_menu()
            return

        old_pause = game.paused
        game.paused = True

        content = BoxLayout(
            orientation="vertical",
            padding=dp(10),
            spacing=dp(8),
        )

        content.add_widget(Label(
            text="Rời ván? Ghi chú và lịch sử chưa xuất sẽ mất."
        ))

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )
        cancel = Button(text="Ở lại")
        accept = Button(text="Rời phòng")
        buttons.add_widget(cancel)
        buttons.add_widget(accept)
        content.add_widget(buttons)

        popup = Popup(
            title="Rời phòng",
            content=content,
            size_hint=(0.85, 0.45),
            auto_dismiss=False,
        )

        def stay(*_):
            game.paused = old_pause
            popup.dismiss()

        def leave_now(*_):
            popup.dismiss()
            self.show_menu()

        cancel.bind(on_release=stay)
        accept.bind(on_release=leave_now)
        popup.open()

    def tick(self, dt):
        game = self.game

        if not game:
            return

        try:
            game.tick(max(0.0, min(dt, 0.25)))

            self.refresh_elapsed += dt

            if self.refresh_elapsed >= 0.2:
                self.refresh_elapsed = 0.0
                self.refresh_info()

        except Exception as error:
            traceback.print_exc()
            game.paused = True
            game.done = True
            self.clear_action()

            self.notice(
                "Lỗi trong ván",
                f"{type(error).__name__}: {error}\n\n"
                "Ván đã dừng. Hãy xuất nhật ký để kiểm tra.",
            )

    def on_pause(self):
        # Android đưa ứng dụng xuống nền:
        # dừng cả đồng hồ và hành động bot.
        if self.game and not self.game.done:
            self.game.paused = True

        return True

    def on_resume(self):
        # Người dùng bấm Tiếp tục sau khi quay lại.
        if self.game:
            self.refresh_info()


if __name__ == "__main__":
    MaSoiApp().run()
