#!/usr/bin/env python3
import sys
import subprocess
import psutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QCheckBox, QLineEdit, QAbstractItemView, QStyle,
    QStyleOptionViewItem, QStyledItemDelegate, QDialog
)
from PyQt6.QtCore import QTimer, Qt, QRectF
from PyQt6.QtGui import QColor, QPen, QPainter


THEME_QSS = """
QMainWindow, QWidget {
    background-color: #1e1f26;
    color: #e6e6e6;
    font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}

QCheckBox {
    spacing: 8px;
    color: #cfd0da;
    padding: 4px 0;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #4a4b5c;
    background: #2b2c37;
}
QCheckBox::indicator:hover {
    border-color: #4f9cf9;
}
QCheckBox::indicator:checked {
    background: #4f9cf9;
    border-color: #4f9cf9;
}

QLineEdit {
    background: #2b2c37;
    border: 1px solid #3a3b4a;
    border-radius: 8px;
    padding: 6px 10px;
    color: #e6e6e6;
    selection-background-color: #4f9cf9;
}
QLineEdit:focus {
    border-color: #4f9cf9;
}

QLabel {
    background: transparent;
}

#statCard {
    background: #262730;
    border: 1px solid #35364a;
    border-radius: 10px;
    padding: 10px 16px;
}

QTableWidget {
    background: #20212a;
    alternate-background-color: #24252f;
    gridline-color: #2f3040;
    border: 1px solid #35364a;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #33384f;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item {
    padding: 6px 10px;
    border: none;
}
QTableWidget::item:selected {
    background: #33384f;
}

QHeaderView::section {
    background: #262730;
    color: #9a9bab;
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid #35364a;
    font-weight: 600;
    font-size: 12px;
}

QScrollBar:vertical {
    background: #20212a;
    width: 12px;
    margin: 4px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #3a3b4a;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #4f9cf9;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #20212a;
    height: 12px;
    margin: 4px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal {
    background: #3a3b4a;
    border-radius: 6px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #4f9cf9;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""


class BadgeDelegate(QStyledItemDelegate):
    """Рисует ячейку типа соединения в виде цветного «пилюльного» бейджа."""

    COLORS = {
        "red": QColor("#e74c3c"),
        "green": QColor("#27ae60"),
        "orange": QColor("#e67e22"),
    }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        color_key = index.data(Qt.ItemDataRole.UserRole)

        # Отрисовываем фон ячейки (выделение / чередование) без текста.
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        if not text:
            return

        color = self.COLORS.get(color_key, QColor("#95a5a6"))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        badge_height = metrics.height() + 8
        badge_width = text_width + 22

        rect = option.rect
        x = rect.x() + (rect.width() - badge_width) / 2
        y = rect.y() + (rect.height() - badge_height) / 2
        badge_rect = QRectF(x, y, badge_width, badge_height)

        bg = QColor(color)
        bg.setAlpha(45)
        painter.setBrush(bg)
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(badge_rect, badge_height / 2, badge_height / 2)

        painter.setPen(color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class NetworkTunnelMonitor(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Network Tunnel & Process Monitor")
        self.resize(1180, 680)
        self.setStyleSheet(THEME_QSS)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(16)

        self.group_by_proc_check = QCheckBox("Группировать по процессам (1 строка)")
        self.group_by_proc_check.setChecked(True)
        self.group_by_proc_check.stateChanged.connect(self.refresh_connections)
        controls_layout.addWidget(self.group_by_proc_check)

        self.hide_daemons_check = QCheckBox("Скрыть xray / happd")
        self.hide_daemons_check.setChecked(True)
        self.hide_daemons_check.stateChanged.connect(self.refresh_connections)
        controls_layout.addWidget(self.hide_daemons_check)

        controls_layout.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Фильтр по процессу или IP...")
        self.search_input.setFixedWidth(280)
        self.search_input.textChanged.connect(self.refresh_connections)
        controls_layout.addWidget(self.search_input)

        layout.addLayout(controls_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self.stat_cards = {}
        self.stat_cards["total"] = self._create_stat_card("Всего сокетов", "#4f9cf9")
        self.stat_cards["tunnel"] = self._create_stat_card("Через VPN / прокси", "#e74c3c")
        self.stat_cards["direct"] = self._create_stat_card("Напрямую", "#27ae60")
        self.stat_cards["core"] = self._create_stat_card("Ядро / демоны", "#e67e22")
        for card in self.stat_cards.values():
            stats_layout.addWidget(card)
        stats_layout.addStretch(1)
        layout.addLayout(stats_layout)

        self.info_label = QLabel("Сканирование соединений...")
        self.info_label.setStyleSheet("color: #8a8b99; font-size: 12px; padding: 2px 4px;")
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Процесс", "PID", "Удаленные адреса / Сокеты", "Локальный интерфейс", "Маршрут / Обработка", "Тип"
        ])

        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setHighlightSections(False)

        self.badge_delegate = BadgeDelegate(self.table)
        self.table.setItemDelegateForColumn(5, self.badge_delegate)

        layout.addWidget(self.table)

        self.table.cellDoubleClicked.connect(self._open_process_sockets)

        self.route_cache = {}

        # Карта: номер строки основной таблицы -> множество реальных PID процесса
        self._row_pids: dict[int, set[int]] = {}

        # Ссылки на открытые дочерние окна (чтобы их не собрал сборщик мусора)
        self._child_windows: list = []

        # Приложения с включенным TUN-прокси в Happ
        self.proxied_apps = ["electron", "shelly-ui", "spotify", "discord"]
        self.tunnel_daemons = ["happd", "xray", "sing-box"]

        # Ключевые слова в имени интерфейса, указывающие на туннель
        self.tunnel_keywords = ["tun", "wg", "sing", "meta", "tap", "tailscale", "ppp", "happ", "xray"]

        # Типичные порты локальных SOCKS5 / HTTP прокси клиентов
        self.common_proxy_ports = {1080, 1081, 10808, 10809, 2080, 2081, 7890, 7891, 8888, 8889, 9050, 9999}

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_connections)
        self.timer.start(2000)

        self.refresh_connections()

    def _create_stat_card(self, title: str, color: str) -> QLabel:
        card = QLabel()
        card.setObjectName("statCard")
        card.setText(
            f'<div style="font-size:22px;font-weight:700;color:{color};">0</div>'
            f'<div style="font-size:11px;color:#8a8b99;">{title}</div>'
        )
        return card

    def _set_stat_value(self, key: str, title: str, color: str, value: int) -> None:
        self.stat_cards[key].setText(
            f'<div style="font-size:22px;font-weight:700;color:{color};">{value}</div>'
            f'<div style="font-size:11px;color:#8a8b99;">{title}</div>'
        )

    def get_route_interface(self, remote_ip: str) -> str:
        if remote_ip in self.route_cache:
            return self.route_cache[remote_ip]

        try:
            cmd = ["ip", "route", "get", remote_ip]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            output = result.stdout.strip()

            parts = output.split()
            if "dev" in parts:
                idx = parts.index("dev") + 1
                if idx < len(parts):
                    dev = parts[idx]
                    self.route_cache[remote_ip] = dev
                    return dev
        except Exception:
            pass

        return "unknown"

    def resolve_proc_info(self, pid: int):
        if not pid:
            return "System / Unknown", ""
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            exe = ""
            try:
                exe = proc.exe()
            except Exception:
                pass

            cmdline = ""
            try:
                cmdline = " ".join(proc.cmdline())
            except Exception:
                pass

            if "firefox" in exe.lower() or "firefox" in cmdline.lower():
                name = "firefox"

            return name, exe
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Завершен / Нет доступа", ""

    def _classify_connection(self, remote_ip, remote_port, proc_name: str, proc_exe: str):
        """Классифицирует соединение: возвращает (dev, gateway_label, tunnel_type, color_type).

        Используется и основным окном, и окном сокетов процесса, чтобы не дублировать логику.
        Корректно работает при отсутствии удалённого адреса (remote_ip is None).
        """
        name_lower = proc_name.lower()
        exe_lower = proc_exe.lower()

        is_daemon = any(daemon in name_lower for daemon in self.tunnel_daemons)
        is_loopback = bool(remote_ip) and (remote_ip.startswith("127.") or remote_ip == "::1")
        is_local_proxy = bool(remote_ip) and is_loopback and (remote_port in self.common_proxy_ports)

        if remote_ip:
            if is_loopback:
                dev = "lo"
            else:
                dev = self.get_route_interface(remote_ip)
        else:
            dev = "—"

        dev_lower = dev.lower()
        is_tun_dev = any(kw in dev_lower for kw in self.tunnel_keywords)
        is_happ_proxied = any(app in name_lower or app in exe_lower for app in self.proxied_apps)

        if is_daemon:
            return dev, f"Туннель ({dev})", "VPN / ЯДРО", "orange"
        if is_local_proxy:
            return dev, f"Внутренний прокси ({remote_ip}:{remote_port})", "VPN / ВНУТР. ПРОКСИ", "red"
        if is_tun_dev:
            if is_happ_proxied:
                return dev, f"Прокси через {dev}", "VPN / ТУННЕЛЬ", "red"
            return dev, f"Direct bypass ({dev})", "НАПРЯМУЮ", "green"
        if not remote_ip:
            return dev, "Локальный сокет", "НАПРЯМУЮ", "green"
        return dev, "Основной шлюз", "НАПРЯМУЮ", "green"

    def refresh_connections(self) -> None:
        try:
            connections = psutil.net_connections(kind="inet")
        except psutil.AccessDenied:
            self.info_label.setText("Внимание: Запустите скрипт через sudo.")
            connections = []

        hide_daemons = self.hide_daemons_check.isChecked()
        group_by_proc = self.group_by_proc_check.isChecked()
        search_filter = self.search_input.text().strip().lower()

        valid_tcp_statuses = {"ESTABLISHED", "SYN_SENT", "SYN_RECV", "CLOSE_WAIT"}
        raw_entries = []

        for conn in connections:
            if conn.type == 1 and conn.status not in valid_tcp_statuses:
                continue

            if not conn.raddr:
                continue

            remote_ip = conn.raddr.ip
            remote_port = conn.raddr.port

            is_loopback = remote_ip.startswith("127.") or remote_ip == "::1"
            is_local_proxy = is_loopback and (remote_port in self.common_proxy_ports)

            # Пропускаем обычный межпроцессный loopback, но ОСТАВЛЯЕМ подключения к локальному прокси
            if is_loopback and not is_local_proxy:
                continue

            pid = conn.pid or 0
            proc_name, proc_exe = self.resolve_proc_info(pid)

            name_lower = proc_name.lower()
            is_daemon = any(daemon in name_lower for daemon in self.tunnel_daemons)
            if hide_daemons and is_daemon:
                continue

            proto_str = "UDP" if conn.type == 2 else "TCP"
            remote_str = f"[{proto_str}] {remote_ip}:{remote_port}"

            # Классификация вынесена в переиспользуемый метод (общий с окном сокетов процесса)
            dev, gateway_label, tunnel_type, color_type = self._classify_connection(
                remote_ip, remote_port, proc_name, proc_exe
            )

            raw_entries.append({
                "process": proc_name,
                "pid": pid,
                "remote": remote_str,
                "dev": dev,
                "gateway": gateway_label,
                "type": tunnel_type,
                "color": color_type
            })

        display_entries = []

        if group_by_proc:
            grouped = {}
            for item in raw_entries:
                key = item["process"]
                if key not in grouped:
                    grouped[key] = {
                        "process": item["process"],
                        "pids": set(),
                        "pids_int": set(),
                        "remotes": [],
                        "devs": set(),
                        "gateway": item["gateway"],
                        "type": item["type"],
                        "color": item["color"],
                        "count": 0
                    }
                grouped[key]["pids"].add(str(item["pid"]))
                grouped[key]["pids_int"].add(item["pid"])
                grouped[key]["remotes"].append(item["remote"])
                grouped[key]["devs"].add(item["dev"])
                grouped[key]["count"] += 1

                # Если хотя бы одно соединение процесса идет в прокси/туннель, весь статус подсвечиваем красным
                if item["color"] == "red":
                    grouped[key]["color"] = "red"
                    grouped[key]["type"] = item["type"]
                    grouped[key]["gateway"] = item["gateway"]

            for key, data in grouped.items():
                pids_str = ", ".join(sorted(data["pids"]))
                devs_str = ", ".join(sorted(data["devs"]))

                sample_remotes = ", ".join(data["remotes"][:2])
                if data["count"] > 2:
                    remotes_summary = f"{sample_remotes} (+{data['count'] - 2} еще)"
                else:
                    remotes_summary = sample_remotes

                display_entries.append({
                    "process": f"{data['process']} ({data['count']})",
                    "pid": pids_str,
                    "pids": set(data["pids_int"]),
                    "proc_name": data["process"],
                    "remote": remotes_summary,
                    "dev": devs_str,
                    "gateway": data["gateway"],
                    "type": data["type"],
                    "color": data["color"],
                    "search_text": f"{data['process']} {pids_str} {' '.join(data['remotes'])}".lower()
                })
        else:
            for item in raw_entries:
                item["search_text"] = f"{item['process']} {item['pid']} {item['remote']}".lower()
                item["pids"] = {item["pid"]}
                item["proc_name"] = item["process"]
                item["pid"] = str(item["pid"])
                display_entries.append(item)

        if search_filter:
            display_entries = [e for e in display_entries if search_filter in e["search_text"]]

        # Детерминированная сортировка, чтобы строки не «мелькали» при автообновлении.
        # Приоритет: красные -> оранжевые -> зелёные, затем процесс, адреса, PID.
        color_priority = {"red": 0, "orange": 1, "green": 2}
        display_entries.sort(
            key=lambda e: (
                color_priority.get(str(e.get("color", "")), 99),
                str(e.get("process", "")).lower(),
                str(e.get("remote", "")),
                str(e.get("pid", "")),
            )
        )

        # Сохраняем реальные PID для каждой строки (для открытия окна сокетов по двойному клику)
        self._row_pids = {
            row: set(entry.get("pids", set()))
            for row, entry in enumerate(display_entries)
        }

        self._update_stats(raw_entries)

        self.table.setRowCount(len(display_entries))
        for row, item in enumerate(display_entries):
            p_item = QTableWidgetItem(item["process"])
            pid_item = QTableWidgetItem(item["pid"])
            rem_item = QTableWidgetItem(item["remote"])
            dev_item = QTableWidgetItem(item["dev"])
            gw_item = QTableWidgetItem(item["gateway"])
            type_item = QTableWidgetItem(item["type"])

            type_item.setData(Qt.ItemDataRole.UserRole, item["color"])
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dev_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, p_item)
            self.table.setItem(row, 1, pid_item)
            self.table.setItem(row, 2, rem_item)
            self.table.setItem(row, 3, dev_item)
            self.table.setItem(row, 4, gw_item)
            self.table.setItem(row, 5, type_item)

        mode_desc = "Группировка" if group_by_proc else "Все сокеты"
        self.info_label.setText(
            f"Строк в таблице: {len(display_entries)} ({mode_desc}) | Всего сокетов: {len(raw_entries)}"
        )

    def _open_process_sockets(self, row: int, column: int) -> None:
        """Открывает немодальное окно со всеми сокетами процесса для выбранной строки."""
        pids = {p for p in self._row_pids.get(row, set()) if p}
        if not pids:
            return

        first_pid = sorted(pids)[0]
        proc_name, _ = self.resolve_proc_info(first_pid)
        if proc_name == "System / Unknown":
            proc_name = "System"

        window = ProcessSocketsWindow(self, pids, proc_name)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.destroyed.connect(lambda _=None, w=window: self._forget_child_window(w))
        self._child_windows.append(window)
        window.show()

    def _forget_child_window(self, window) -> None:
        try:
            self._child_windows.remove(window)
        except ValueError:
            pass

    def _update_stats(self, raw_entries) -> None:
        counts = {"red": 0, "green": 0, "orange": 0}
        for item in raw_entries:
            counts[item["color"]] = counts.get(item["color"], 0) + 1

        self._set_stat_value("total", "Всего сокетов", "#4f9cf9", len(raw_entries))
        self._set_stat_value("tunnel", "Через VPN / прокси", "#e74c3c", counts["red"])
        self._set_stat_value("direct", "Напрямую", "#27ae60", counts["green"])
        self._set_stat_value("core", "Ядро / демоны", "#e67e22", counts["orange"])


class ProcessSocketsWindow(QDialog):
    """Немодальное окно со ВСЕМИ сокетами выбранного процесса (без фильтров основного окна)."""

    def __init__(self, monitor: NetworkTunnelMonitor, pids: set, proc_name: str) -> None:
        super().__init__(monitor)
        self.monitor = monitor
        self.pids = set(pids)
        self.proc_name = proc_name

        pids_title = ", ".join(str(p) for p in sorted(self.pids))
        self.setWindowTitle(f"Сокеты процесса: {proc_name} (PID: {pids_title})")
        self.resize(980, 560)
        self.setStyleSheet(THEME_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.info_label = QLabel("Сканирование сокетов...")
        self.info_label.setStyleSheet("color: #8a8b99; font-size: 12px; padding: 2px 4px;")
        layout.addWidget(self.info_label)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Протокол", "Локальный адрес", "Удалённый адрес", "Статус",
            "PID", "Интерфейс", "Тип"
        ])
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setHighlightSections(False)

        self.badge_delegate = BadgeDelegate(self.table)
        self.table.setItemDelegateForColumn(6, self.badge_delegate)

        layout.addWidget(self.table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_sockets)
        self.timer.start(2000)

        self.refresh_sockets()

    @staticmethod
    def _format_addr(addr) -> str:
        if not addr:
            return "—"
        return f"{addr.ip}:{addr.port}"

    def refresh_sockets(self) -> None:
        try:
            connections = psutil.net_connections(kind="inet")
        except psutil.AccessDenied:
            self.info_label.setText("Внимание: Запустите скрипт через sudo.")
            connections = []

        entries = []
        for conn in connections:
            if conn.pid not in self.pids:
                continue

            proto_str = "UDP" if conn.type == 2 else "TCP"
            laddr = conn.laddr
            raddr = conn.raddr
            remote_ip = raddr.ip if raddr else None
            remote_port = raddr.port if raddr else None

            proc_name, proc_exe = self.monitor.resolve_proc_info(conn.pid or 0)
            dev, _gateway, tunnel_type, color_type = self.monitor._classify_connection(
                remote_ip, remote_port, proc_name, proc_exe
            )

            if conn.type == 1:
                status = conn.status or "—"
            else:
                status = "—"

            entries.append({
                "proto": proto_str,
                "laddr": f"{laddr.ip}:{laddr.port}" if laddr else "—",
                "raddr": self._format_addr(raddr),
                "status": status,
                "pid": str(conn.pid),
                "dev": dev,
                "type": tunnel_type,
                "color": color_type,
            })

        # Детерминированная сортировка, чтобы строки не «мелькали» при автообновлении
        entries.sort(
            key=lambda e: (
                str(e["pid"]),
                e["proto"],
                e["laddr"],
                e["raddr"],
                e["status"],
            )
        )

        self.table.setRowCount(len(entries))
        for row, item in enumerate(entries):
            proto_item = QTableWidgetItem(item["proto"])
            laddr_item = QTableWidgetItem(item["laddr"])
            raddr_item = QTableWidgetItem(item["raddr"])
            status_item = QTableWidgetItem(item["status"])
            pid_item = QTableWidgetItem(item["pid"])
            dev_item = QTableWidgetItem(item["dev"])
            type_item = QTableWidgetItem(item["type"])

            type_item.setData(Qt.ItemDataRole.UserRole, item["color"])
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dev_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            proto_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, proto_item)
            self.table.setItem(row, 1, laddr_item)
            self.table.setItem(row, 2, raddr_item)
            self.table.setItem(row, 3, status_item)
            self.table.setItem(row, 4, pid_item)
            self.table.setItem(row, 5, dev_item)
            self.table.setItem(row, 6, type_item)

        self.info_label.setText(
            f"Сокетов процесса: {len(entries)} | PID: "
            f"{', '.join(str(p) for p in sorted(self.pids))}"
        )


def main() -> None:
    app = QApplication(sys.argv)
    window = NetworkTunnelMonitor()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
