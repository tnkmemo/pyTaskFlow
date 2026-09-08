import json
import math
import os
import subprocess
import sys
import webbrowser
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QToolBar,
)

STATUS_COLORS = {
    "未着手": QColor("#E5E7EB"),
    "進行中": QColor("#BFDBFE"),
    "完了": QColor("#BBF7D0"),
    "保留": QColor("#FDE68A"),
}


def open_link(link: str) -> None:
    if not link:
        return

    parsed = urlparse(link)
    if parsed.scheme in {"http", "https"}:
        webbrowser.open(link)
        return

    target = Path(link).expanduser()
    if not target.exists():
        QMessageBox.warning(None, "パスが見つかりません", f"次のパスは存在しません。\n{target}")
        return

    if sys.platform.startswith("win"):
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def get_task_link(task: dict) -> str:
    return task.get("link") or task.get("folder") or ""


def get_artifact_link(artifact: dict) -> str:
    return artifact.get("link") or artifact.get("folder") or ""


def normalize_id_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def artifact_label(artifact: dict) -> str:
    artifact_id = artifact.get("id", "")
    name = artifact.get("name") or artifact_id or "Unnamed"
    artifact_type = artifact.get("type", "")
    if artifact_id and artifact_id != name:
        label = f"{artifact_id}  {name}"
    else:
        label = str(name)
    if artifact_type:
        label = f"{label} ({artifact_type})"
    return label


class EdgeItem(QGraphicsPathItem):
    def __init__(self, source_node, target_node):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.setZValue(-1)
        self.setPen(QPen(QColor("#4B5563"), 2))
        self.update_path()

    def update_path(self):
        src_rect = self.source_node.sceneBoundingRect()
        dst_rect = self.target_node.sceneBoundingRect()

        p1 = QPointF(src_rect.right(), src_rect.center().y())
        p2 = QPointF(dst_rect.left(), dst_rect.center().y())

        dx = max(70.0, (p2.x() - p1.x()) * 0.45)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())

        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        path = self.path()
        if path.isEmpty():
            return

        end = path.pointAtPercent(1.0)
        prev = path.pointAtPercent(0.97)
        angle = math.atan2(end.y() - prev.y(), end.x() - prev.x())
        arrow_size = 10

        p_a = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6),
            end.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        p_b = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6),
            end.y() - arrow_size * math.sin(angle + math.pi / 6),
        )

        painter.setBrush(QBrush(QColor("#4B5563")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([end, p_a, p_b]))


class ResourceTextItem(QGraphicsTextItem):
    def __init__(self, text: str, artifact: dict, parent=None):
        super().__init__(text, parent)
        self.artifact = artifact
        self.setDefaultTextColor(QColor("#1F2937"))
        self.setTextWidth(TaskNodeItem.WIDTH - 22)
        if get_artifact_link(artifact):
            self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        link = get_artifact_link(self.artifact)
        if link:
            open_link(link)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TaskNodeItem(QGraphicsRectItem):
    WIDTH = 180
    HEIGHT = 96
    RESOURCE_LINE_HEIGHT = 22
    RESOURCE_SECTION_HEIGHT = 20
    RESOURCE_BOTTOM_MARGIN = 10

    def __init__(self, task: dict, app_window):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.task = task
        self.app_window = app_window
        self.edges = []
        self.expanded = False
        self.resource_items = []

        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPen(QPen(QColor("#374151"), 1.5))
        self.setBrush(QBrush(STATUS_COLORS.get(task.get("status"), QColor("#FFFFFF"))))

        self.title_item = QGraphicsTextItem(self)
        self.title_item.setDefaultTextColor(QColor("#111827"))
        self.title_item.setTextWidth(self.WIDTH - 20)
        self.title_item.setPos(10, 8)

        self.subtitle_item = QGraphicsTextItem(self)
        self.subtitle_item.setDefaultTextColor(QColor("#4B5563"))
        self.subtitle_item.setTextWidth(self.WIDTH - 20)
        self.subtitle_item.setPos(10, 34)

        self.artifact_item = QGraphicsTextItem(self)
        self.artifact_item.setDefaultTextColor(QColor("#374151"))
        self.artifact_item.setTextWidth(self.WIDTH - 20)
        self.artifact_item.setPos(10, 60)

        self.refresh_text()
        self.setPos(float(task.get("x", 0)), float(task.get("y", 0)))

    @property
    def task_id(self):
        return self.task["id"]

    def refresh_text(self):
        self.title_item.setPlainText(f'{self.task["id"]}  {self.task["name"]}')
        self.subtitle_item.setPlainText(f'状態: {self.task.get("status", "未着手")}')
        inputs = len(normalize_id_list(self.task.get("inputs")))
        outputs = len(normalize_id_list(self.task.get("outputs")))
        resources = len(normalize_id_list(self.task.get("resources")))
        self.artifact_item.setPlainText(f"成果物  入:{inputs}  出:{outputs}  資料:{resources}")
        self.setBrush(QBrush(STATUS_COLORS.get(self.task.get("status"), QColor("#FFFFFF"))))
        if self.expanded:
            self.refresh_resources()

    def add_edge(self, edge):
        self.edges.append(edge)

    def update_edges(self):
        for edge in self.edges:
            edge.update_path()

    def clear_resource_items(self):
        for item in self.resource_items:
            if item.scene() is not None:
                item.scene().removeItem(item)
            item.setParentItem(None)
        self.resource_items = []

    def resource_sections(self):
        return [
            ("入力", self.app_window.get_task_artifacts(self.task, "inputs")),
            ("出力", self.app_window.get_task_artifacts(self.task, "outputs")),
            ("資料", self.app_window.get_task_artifacts(self.task, "resources")),
        ]

    def refresh_resources(self):
        self.clear_resource_items()
        y = self.HEIGHT

        sections = [(title, artifacts) for title, artifacts in self.resource_sections() if artifacts]
        if not sections:
            item = QGraphicsTextItem("関連リソースなし", self)
            item.setDefaultTextColor(QColor("#6B7280"))
            item.setTextWidth(self.WIDTH - 22)
            item.setPos(10, y)
            self.resource_items.append(item)
            y += self.RESOURCE_LINE_HEIGHT
        else:
            for title, artifacts in sections:
                header = QGraphicsTextItem(title, self)
                header.setDefaultTextColor(QColor("#111827"))
                header.setTextWidth(self.WIDTH - 22)
                header.setPos(10, y)
                self.resource_items.append(header)
                y += self.RESOURCE_SECTION_HEIGHT

                for artifact in artifacts:
                    item = ResourceTextItem(f"- {artifact_label(artifact)}", artifact, self)
                    item.setPos(14, y)
                    self.resource_items.append(item)
                    y += self.RESOURCE_LINE_HEIGHT

        self.setRect(0, 0, self.WIDTH, y + self.RESOURCE_BOTTOM_MARGIN)
        self.update_edges()

    def set_expanded(self, expanded: bool):
        if self.expanded == expanded:
            return

        self.expanded = expanded
        if expanded:
            self.refresh_resources()
        else:
            self.clear_resource_items()
            self.setRect(0, 0, self.WIDTH, self.HEIGHT)
            self.update_edges()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.task["x"] = value.x()
            self.task["y"] = value.y()
            self.update_edges()
            if self.scene() is not None and not self.app_window._layout_in_progress:
                self.app_window.set_modified(True)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.app_window.expand_task_node(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        link = get_task_link(self.task)
        if link:
            open_link(link)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        open_action = menu.addAction("リンクを開く")
        open_action.setEnabled(bool(get_task_link(self.task)))

        artifact_actions = {}
        input_menu = menu.addMenu("入力成果物を開く")
        input_artifacts = self.app_window.get_task_artifacts(self.task, "inputs")
        input_menu.setEnabled(bool(input_artifacts))
        for artifact in input_artifacts:
            action = input_menu.addAction(self.app_window.artifact_menu_label(artifact))
            action.setEnabled(bool(get_artifact_link(artifact)))
            artifact_actions[action] = artifact

        output_menu = menu.addMenu("出力成果物を開く")
        output_artifacts = self.app_window.get_task_artifacts(self.task, "outputs")
        output_menu.setEnabled(bool(output_artifacts))
        for artifact in output_artifacts:
            action = output_menu.addAction(self.app_window.artifact_menu_label(artifact))
            action.setEnabled(bool(get_artifact_link(artifact)))
            artifact_actions[action] = artifact

        resource_menu = menu.addMenu("資料を開く")
        resource_artifacts = self.app_window.get_task_artifacts(self.task, "resources")
        resource_menu.setEnabled(bool(resource_artifacts))
        for artifact in resource_artifacts:
            action = resource_menu.addAction(self.app_window.artifact_menu_label(artifact))
            action.setEnabled(bool(get_artifact_link(artifact)))
            artifact_actions[action] = artifact

        status_menu = menu.addMenu("状態を変更")
        status_actions = {}
        for status in STATUS_COLORS:
            action = status_menu.addAction(status)
            action.setCheckable(True)
            action.setChecked(self.task.get("status") == status)
            status_actions[action] = status

        selected = menu.exec(event.screenPos())
        if selected == open_action:
            open_link(get_task_link(self.task))
        elif selected in artifact_actions:
            open_link(get_artifact_link(artifact_actions[selected]))
        elif selected in status_actions:
            self.task["status"] = status_actions[selected]
            self.refresh_text()
            self.app_window.set_modified(True)


class DependencyView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    COLUMN_SPACING = 300
    ROW_SPACING = 130

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskFlow Auto Layout Sample")
        self.resize(1250, 780)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(QRectF(-1000, -1000, 5000, 4000))
        self.view = DependencyView(self.scene)
        self.setCentralWidget(self.view)

        self.nodes = {}
        self.edges = []
        self.tasks = {}
        self.artifacts = {}
        self.project = {"tasks": [], "artifacts": [], "dependencies": []}
        self.expanded_node = None
        self.current_file = None
        self.modified = False
        self._layout_in_progress = False

        self.build_toolbar()
        self.statusBar().showMessage("JSONを開くか、サンプルを読み込んでください")

    def build_toolbar(self):
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        open_action = QAction("JSONを開く", self)
        open_action.triggered.connect(self.open_json)
        toolbar.addAction(open_action)

        save_action = QAction("保存", self)
        save_action.triggered.connect(self.save_json)
        toolbar.addAction(save_action)

        save_as_action = QAction("名前を付けて保存", self)
        save_as_action.triggered.connect(self.save_json_as)
        toolbar.addAction(save_as_action)

        toolbar.addSeparator()

        auto_action = QAction("完全自動配置", self)
        auto_action.setToolTip("依存関係から列と行の両方を自動配置します")
        auto_action.triggered.connect(self.auto_layout_full)
        toolbar.addAction(auto_action)

        column_action = QAction("列だけ整列", self)
        column_action.setToolTip("依存関係からX座標だけを自動配置し、Y座標は維持します")
        column_action.triggered.connect(self.auto_layout_columns_only)
        toolbar.addAction(column_action)

        toolbar.addSeparator()

        fit_action = QAction("全体表示", self)
        fit_action.triggered.connect(self.fit_all)
        toolbar.addAction(fit_action)

    def set_modified(self, modified=True):
        self.modified = modified
        marker = "*" if modified else ""
        filename = self.current_file.name if self.current_file else "TaskFlow"
        self.setWindowTitle(f"{filename}{marker}")

    def clear_graph(self):
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.tasks.clear()
        self.artifacts.clear()
        self.expanded_node = None

    def expand_task_node(self, node: TaskNodeItem):
        if self.expanded_node is not None and self.expanded_node is not node:
            self.expanded_node.set_expanded(False)
        self.expanded_node = node
        node.set_expanded(True)

    def task_label(self, task_id: str) -> str:
        task = self.tasks.get(task_id)
        if not task:
            return task_id
        name = task.get("name")
        if name:
            return f"{task_id} {name}"
        return task_id

    def infer_artifact_producer(self, artifact_id: str) -> str:
        for task in self.project.get("tasks", []):
            if artifact_id in normalize_id_list(task.get("outputs")):
                return str(task.get("id", ""))
        return ""

    def infer_artifact_consumers(self, artifact_id: str) -> list[str]:
        consumers = []
        for task in self.project.get("tasks", []):
            task_id = task.get("id")
            task_inputs = normalize_id_list(task.get("inputs"))
            task_resources = normalize_id_list(task.get("resources"))
            if task_id and artifact_id in task_inputs + task_resources:
                consumers.append(str(task_id))
        return consumers

    def artifact_menu_label(self, artifact: dict) -> str:
        label = artifact_label(artifact)
        artifact_id = str(artifact.get("id", ""))
        producer = artifact.get("producer") or self.infer_artifact_producer(artifact_id)
        consumers = normalize_id_list(artifact.get("consumers")) or self.infer_artifact_consumers(artifact_id)

        details = []
        if producer:
            details.append(f"作成:{self.task_label(str(producer))}")
        if consumers:
            consumer_labels = ", ".join(self.task_label(task_id) for task_id in consumers)
            details.append(f"使用:{consumer_labels}")

        if details:
            return f"{label} / {' / '.join(details)}"
        return label

    def get_task_artifacts(self, task: dict, field: str) -> list[dict]:
        artifacts = []
        for artifact_id in normalize_id_list(task.get(field)):
            artifact = self.artifacts.get(artifact_id)
            if artifact:
                artifacts.append(artifact)
        return artifacts

    def load_project(self, project: dict):
        self._layout_in_progress = True
        try:
            self.clear_graph()
            self.project = project
            self.tasks = {
                str(task.get("id")): task
                for task in project.get("tasks", [])
                if task.get("id")
            }
            self.artifacts = {
                str(artifact.get("id")): artifact
                for artifact in project.get("artifacts", [])
                if artifact.get("id")
            }

            for task in project.get("tasks", []):
                node = TaskNodeItem(task, self)
                self.scene.addItem(node)
                self.nodes[node.task_id] = node

            for dep in project.get("dependencies", []):
                source = self.nodes.get(dep.get("from"))
                target = self.nodes.get(dep.get("to"))
                if source and target:
                    edge = EdgeItem(source, target)
                    self.scene.addItem(edge)
                    source.add_edge(edge)
                    target.add_edge(edge)
                    self.edges.append(edge)
        finally:
            self._layout_in_progress = False

        self.fit_all()
        self.set_modified(False)

    def open_json(self):
        filename, _ = QFileDialog.getOpenFileName(self, "プロジェクトJSONを開く", "", "JSON Files (*.json)")
        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                project = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "読込エラー", str(e))
            return

        self.current_file = Path(filename)
        self.load_project(project)
        self.statusBar().showMessage(str(self.current_file))

    def sync_positions(self):
        for node in self.nodes.values():
            node.task["x"] = node.pos().x()
            node.task["y"] = node.pos().y()

    def save_json(self):
        if not self.current_file:
            self.save_json_as()
            return

        self.sync_positions()
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(self.project, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))
            return

        self.set_modified(False)
        self.statusBar().showMessage(f"保存しました: {self.current_file}", 3000)

    def save_json_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "名前を付けて保存",
            str(self.current_file or "project.json"),
            "JSON Files (*.json)",
        )
        if not filename:
            return

        if not filename.lower().endswith(".json"):
            filename += ".json"

        self.current_file = Path(filename)
        self.save_json()

    def build_graph_maps(self):
        task_ids = list(self.nodes.keys())
        predecessors = {task_id: [] for task_id in task_ids}
        successors = {task_id: [] for task_id in task_ids}

        for dep in self.project.get("dependencies", []):
            src = dep.get("from")
            dst = dep.get("to")
            if src in self.nodes and dst in self.nodes:
                successors[src].append(dst)
                predecessors[dst].append(src)

        return predecessors, successors

    def calculate_columns(self):
        """依存関係の深さから列番号を計算。循環依存も検出する。"""
        predecessors, successors = self.build_graph_maps()
        indegree = {task_id: len(predecessors[task_id]) for task_id in self.nodes}

        queue = deque(sorted([tid for tid, degree in indegree.items() if degree == 0], key=str))
        columns = {task_id: 0 for task_id in queue}
        processed = 0

        while queue:
            current = queue.popleft()
            processed += 1

            for nxt in successors[current]:
                columns[nxt] = max(columns.get(nxt, 0), columns[current] + 1)
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        if processed != len(self.nodes):
            raise ValueError(
                "循環依存を検出しました。\n"
                "例: T01 → T02 → T03 → T01 のような依存関係が存在しています。"
            )

        return columns, predecessors, successors

    def order_rows_to_reduce_crossings(self, columns, predecessors, successors):
        """barycenter法の簡易版で、同じ列内の並び順を調整する。"""
        grouped = defaultdict(list)
        for task_id, col in columns.items():
            grouped[col].append(task_id)

        for col in grouped:
            grouped[col].sort(key=lambda tid: (self.nodes[tid].pos().y(), str(tid)))

        max_col = max(grouped.keys(), default=0)

        def positions(col):
            return {task_id: i for i, task_id in enumerate(grouped[col])}

        for _ in range(6):
            for col in range(1, max_col + 1):
                if col not in grouped:
                    continue
                prev_positions = positions(col - 1) if (col - 1) in grouped else {}
                old_index = {tid: i for i, tid in enumerate(grouped[col])}

                def forward_key(task_id):
                    linked = [prev_positions[p] for p in predecessors[task_id] if p in prev_positions]
                    bary = sum(linked) / len(linked) if linked else old_index[task_id]
                    return (bary, old_index[task_id], str(task_id))

                grouped[col].sort(key=forward_key)

            for col in range(max_col - 1, -1, -1):
                if col not in grouped:
                    continue
                next_positions = positions(col + 1) if (col + 1) in grouped else {}
                old_index = {tid: i for i, tid in enumerate(grouped[col])}

                def backward_key(task_id):
                    linked = [next_positions[s] for s in successors[task_id] if s in next_positions]
                    bary = sum(linked) / len(linked) if linked else old_index[task_id]
                    return (bary, old_index[task_id], str(task_id))

                grouped[col].sort(key=backward_key)

        return grouped

    def calculate_centered_y_positions(self, grouped, predecessors):
        """後続ノードを前提ノード群の中央へ寄せつつ、行間隔を確保する。"""
        y_positions = {}
        min_gap = self.ROW_SPACING

        for col in sorted(grouped):
            task_ids = grouped[col]
            desired = []

            for row, task_id in enumerate(task_ids):
                preds = [p for p in predecessors[task_id] if p in y_positions]
                if preds:
                    desired.append(sum(y_positions[p] for p in preds) / len(preds))
                else:
                    desired.append(row * min_gap)

            placed = []
            for i, y in enumerate(desired):
                if i == 0:
                    placed.append(y)
                else:
                    placed.append(max(y, placed[-1] + min_gap))

            if placed:
                target_center = sum(desired) / len(desired)
                actual_center = sum(placed) / len(placed)
                shift = target_center - actual_center
                placed = [y + shift for y in placed]

            for task_id, y in zip(task_ids, placed):
                y_positions[task_id] = y

        if y_positions:
            min_y = min(y_positions.values())
            for task_id in y_positions:
                y_positions[task_id] -= min_y

        return y_positions

    def auto_layout_full(self):
        try:
            columns, predecessors, successors = self.calculate_columns()
        except ValueError as e:
            QMessageBox.warning(self, "自動配置できません", str(e))
            return

        grouped = self.order_rows_to_reduce_crossings(columns, predecessors, successors)
        y_positions = self.calculate_centered_y_positions(grouped, predecessors)

        self._layout_in_progress = True
        try:
            for task_id, node in self.nodes.items():
                x = columns[task_id] * self.COLUMN_SPACING
                y = y_positions[task_id]
                node.setPos(x, y)
                node.task["x"] = x
                node.task["y"] = y

            for edge in self.edges:
                edge.update_path()
        finally:
            self._layout_in_progress = False

        self.set_modified(True)
        self.fit_all()
        self.statusBar().showMessage(
            "完全自動配置: 依存階層で列を決定し、行順と中央寄せを自動調整しました",
            4000,
        )

    def auto_layout_columns_only(self):
        try:
            columns, _, _ = self.calculate_columns()
        except ValueError as e:
            QMessageBox.warning(self, "自動配置できません", str(e))
            return

        self._layout_in_progress = True
        try:
            for task_id, node in self.nodes.items():
                x = columns[task_id] * self.COLUMN_SPACING
                y = node.pos().y()
                node.setPos(x, y)
                node.task["x"] = x
                node.task["y"] = y

            for edge in self.edges:
                edge.update_path()
        finally:
            self._layout_in_progress = False

        self.set_modified(True)
        self.fit_all()
        self.statusBar().showMessage(
            "列だけ整列: X座標を依存階層に合わせ、Y座標は維持しました",
            4000,
        )

    def fit_all(self):
        rect = self.scene.itemsBoundingRect()
        if not rect.isNull():
            self.view.fitInView(rect.adjusted(-80, -80, 80, 80), Qt.KeepAspectRatio)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    sample = Path(__file__).with_name("sample_project.json")
    if sample.exists():
        try:
            with open(sample, "r", encoding="utf-8") as f:
                window.current_file = sample
                window.load_project(json.load(f))
                window.statusBar().showMessage("「完全自動配置」を押すと依存関係から行列配置します")
        except Exception:
            pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
