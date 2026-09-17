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
from PySide6.QtGui import QAction, QBrush, QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDoubleSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

STATUS_COLORS = {
    "未着手": QColor("#E5E7EB"),
    "進行中": QColor("#BFDBFE"),
    "完了": QColor("#BBF7D0"),
    "保留": QColor("#FDE68A"),
}

STATUS_OPTIONS = list(STATUS_COLORS.keys())
ARTIFACT_KIND_OPTIONS = ["artifact", "manual", "reference", "template"]
GROUP_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF3C7", "#FCE7F3", "#EDE9FE", "#CCFBF1", "#FFE4E6"]


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
    if artifact_id and artifact_id != name:
        return f"{artifact_id}  {name}"
    return str(name)


def task_group(task: dict) -> str:
    return str(task.get("group", "")).strip()


class EdgeItem(QGraphicsPathItem):
    def __init__(self, source_node, target_node, dependency: dict, app_window):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.dependency = dependency
        self.app_window = app_window
        self.hovered = False
        self.default_color = QColor("#4B5563")
        self.selected_color = QColor("#2563EB")
        self.hover_color = QColor("#111827")
        self.setZValue(-1)
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"依存関係: {self.label()}\n右クリックで解除")
        self.refresh_style()
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

    def label(self) -> str:
        return f"{self.dependency.get('from', '')} -> {self.dependency.get('to', '')}"

    def refresh_style(self):
        if self.isSelected():
            color = self.selected_color
            width = 3
        elif self.hovered:
            color = self.hover_color
            width = 3
        else:
            color = self.default_color
            width = 2
        self.setPen(QPen(color, width))

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path()).united(super().shape())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.refresh_style()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.hovered = True
        self.refresh_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hovered = False
        self.refresh_style()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.app_window.is_dependency_pick_mode:
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.app_window.select_dependency_edge(self):
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        select_action = menu.addAction("依存関係を選択")
        remove_action = menu.addAction(f"依存関係を解除: {self.label()}")
        selected = menu.exec(event.screenPos())
        if selected == select_action:
            self.app_window.select_dependency_edge(self)
        elif selected == remove_action:
            self.app_window.delete_dependency_edge(self)

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

        painter.setBrush(QBrush(self.pen().color()))
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

    def mousePressEvent(self, event):
        link = get_artifact_link(self.artifact)
        if event.button() == Qt.LeftButton and link:
            open_link(link)
            event.accept()
            return
        super().mousePressEvent(event)


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
        self.title_item.setAcceptedMouseButtons(Qt.NoButton)

        self.subtitle_item = QGraphicsTextItem(self)
        self.subtitle_item.setDefaultTextColor(QColor("#4B5563"))
        self.subtitle_item.setTextWidth(self.WIDTH - 20)
        self.subtitle_item.setPos(10, 34)
        self.subtitle_item.setAcceptedMouseButtons(Qt.NoButton)

        self.artifact_item = QGraphicsTextItem(self)
        self.artifact_item.setDefaultTextColor(QColor("#374151"))
        self.artifact_item.setTextWidth(self.WIDTH - 20)
        self.artifact_item.setPos(10, 60)
        self.artifact_item.setAcceptedMouseButtons(Qt.NoButton)

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

    def refresh_style(self):
        if self.app_window.dependency_source_id == self.task_id:
            self.setPen(QPen(QColor("#2563EB"), 3))
        elif self.app_window.is_dependency_pick_mode:
            if self.app_window.dependency_source_id is None or self.app_window.can_add_dependency_to(self.task_id):
                self.setPen(QPen(QColor("#059669"), 2.5, Qt.DashLine))
            else:
                self.setPen(QPen(QColor("#9CA3AF"), 1, Qt.DotLine))
        elif self.isSelected():
            self.setPen(QPen(QColor("#111827"), 2.5))
        else:
            self.setPen(QPen(QColor("#374151"), 1.5))

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
            item.setAcceptedMouseButtons(Qt.NoButton)
            self.resource_items.append(item)
            y += self.RESOURCE_LINE_HEIGHT
        else:
            for title, artifacts in sections:
                header = QGraphicsTextItem(title, self)
                header.setDefaultTextColor(QColor("#111827"))
                header.setTextWidth(self.WIDTH - 22)
                header.setPos(10, y)
                header.setAcceptedMouseButtons(Qt.NoButton)
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
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self.refresh_style()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.app_window.handle_dependency_target_click(self):
                event.accept()
                return
            self.app_window.select_task_node(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.app_window.toggle_task_node(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self.app_window._layout_in_progress:
            self.app_window.update_group_items()
            self.app_window.update_json_preview()

    def contextMenuEvent(self, event):
        menu = QMenu()
        open_action = menu.addAction("リンクを開く")
        open_action.setEnabled(bool(get_task_link(self.task)))

        artifact_actions = {}
        input_menu = menu.addMenu("入力成果物を開く")
        input_artifacts = self.app_window.get_task_artifacts(self.task, "inputs")
        input_menu.setEnabled(bool(input_artifacts))
        for artifact in input_artifacts:
            action = input_menu.addAction(artifact_label(artifact))
            action.setEnabled(bool(get_artifact_link(artifact)))
            artifact_actions[action] = artifact

        output_menu = menu.addMenu("出力成果物を開く")
        output_artifacts = self.app_window.get_task_artifacts(self.task, "outputs")
        output_menu.setEnabled(bool(output_artifacts))
        for artifact in output_artifacts:
            action = output_menu.addAction(artifact_label(artifact))
            action.setEnabled(bool(get_artifact_link(artifact)))
            artifact_actions[action] = artifact

        resource_menu = menu.addMenu("資料を開く")
        resource_artifacts = self.app_window.get_task_artifacts(self.task, "resources")
        resource_menu.setEnabled(bool(resource_artifacts))
        for artifact in resource_artifacts:
            action = resource_menu.addAction(artifact_label(artifact))
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
    def __init__(self, scene, app_window):
        super().__init__(scene)
        self.app_window = app_window
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if self.app_window.task_node_for_item(item) is None and self.app_window.handle_canvas_empty_click():
                event.accept()
                return
        super().mousePressEvent(event)

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
    NODE_VERTICAL_GAP = 24

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskFlow Auto Layout Sample")
        self.resize(1250, 780)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(QRectF(-1000, -1000, 5000, 4000))
        self.view = DependencyView(self.scene, self)
        self.setCentralWidget(self.view)

        self.nodes = {}
        self.edges = []
        self.group_items = []
        self.tasks = {}
        self.artifacts = {}
        self.project = {"tasks": [], "artifacts": [], "dependencies": []}
        self.expanded_node = None
        self.current_file = None
        self.modified = False
        self._layout_in_progress = False
        self._updating_editor = False
        self.selected_kind = None
        self.selected_id = None
        self.is_dependency_pick_mode = False
        self.dependency_source_id = None

        self.build_toolbar()
        self.build_editor_ui()
        self.statusBar().showMessage("JSONを開くか、サンプルを読み込んでください")

    def build_toolbar(self):
        self.toolbar = QToolBar("Main")
        self.addToolBar(self.toolbar)

        new_action = QAction("新規", self)
        new_action.triggered.connect(self.new_project)
        self.toolbar.addAction(new_action)

        open_action = QAction("JSONを開く", self)
        open_action.triggered.connect(self.open_json)
        self.toolbar.addAction(open_action)

        save_action = QAction("保存", self)
        save_action.triggered.connect(self.save_json)
        self.toolbar.addAction(save_action)

        save_as_action = QAction("名前を付けて保存", self)
        save_as_action.triggered.connect(self.save_json_as)
        self.toolbar.addAction(save_as_action)

        self.toolbar.addSeparator()

        auto_action = QAction("完全自動配置", self)
        auto_action.setToolTip("依存関係から列と行の両方を自動配置します")
        auto_action.triggered.connect(self.auto_layout_full)
        self.toolbar.addAction(auto_action)

        column_action = QAction("列だけ整列", self)
        column_action.setToolTip("依存関係からX座標だけを自動配置し、Y座標は維持します")
        column_action.triggered.connect(self.auto_layout_columns_only)
        self.toolbar.addAction(column_action)

        self.toolbar.addSeparator()

        self.add_dependency_action = QAction("依存追加", self)
        self.add_dependency_action.setCheckable(True)
        self.add_dependency_action.setToolTip("1番目にクリックしたタスクから、2番目にクリックしたタスクへ依存関係を追加します")
        self.add_dependency_action.triggered.connect(self.toggle_dependency_pick_mode)
        self.toolbar.addAction(self.add_dependency_action)

        self.toolbar.addSeparator()

        fit_action = QAction("全体表示", self)
        fit_action.triggered.connect(self.fit_all)
        self.toolbar.addAction(fit_action)

    def build_editor_ui(self):
        self.project_dock = QDockWidget("Project", self)
        self.project_dock.setObjectName("projectDock")
        project_widget = QWidget()
        project_layout = QVBoxLayout(project_widget)

        self.project_tabs = QTabWidget()
        self.task_list = QListWidget()
        self.artifact_list = QListWidget()
        self.dependency_list = QListWidget()
        for list_widget in (self.task_list, self.artifact_list, self.dependency_list):
            list_widget.setSelectionMode(QAbstractItemView.SingleSelection)

        self.project_tabs.addTab(self.task_list, "Tasks")
        self.project_tabs.addTab(self.artifact_list, "Artifacts")
        self.project_tabs.addTab(self.dependency_list, "Dependencies")
        project_layout.addWidget(self.project_tabs)

        button_row = QHBoxLayout()
        add_button = QPushButton("追加")
        delete_button = QPushButton("削除")
        add_button.clicked.connect(self.add_selected_tab_item)
        delete_button.clicked.connect(self.delete_selected_item)
        button_row.addWidget(add_button)
        button_row.addWidget(delete_button)
        project_layout.addLayout(button_row)

        self.project_dock.setWidget(project_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)

        self.task_list.currentItemChanged.connect(self.on_task_item_selected)
        self.artifact_list.currentItemChanged.connect(self.on_artifact_item_selected)
        self.dependency_list.currentItemChanged.connect(self.on_dependency_item_selected)

        self.editor_dock = QDockWidget("Editor", self)
        self.editor_dock.setObjectName("editorDock")
        editor_tabs = QTabWidget()
        editor_tabs.addTab(self.build_form_stack(), "Edit")
        self.json_preview = QPlainTextEdit()
        self.json_preview.setReadOnly(True)
        editor_tabs.addTab(self.json_preview, "JSON")
        self.editor_dock.setWidget(editor_tabs)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.editor_dock)
        self.splitDockWidget(self.project_dock, self.editor_dock, Qt.Vertical)
        self.resizeDocks([self.project_dock, self.editor_dock], [280, 420], Qt.Vertical)
        self.resizeDocks([self.project_dock, self.editor_dock], [380, 380], Qt.Horizontal)

        self.toolbar.addSeparator()
        self.toolbar.addAction(self.project_dock.toggleViewAction())
        self.toolbar.addAction(self.editor_dock.toggleViewAction())

        self.refresh_editor()

    def build_form_stack(self):
        self.form_stack = QStackedWidget()
        empty = QLabel("左の一覧から編集する項目を選択してください")
        empty.setAlignment(Qt.AlignCenter)
        self.form_stack.addWidget(empty)
        self.form_stack.addWidget(self.build_task_form())
        self.form_stack.addWidget(self.build_artifact_form())
        self.form_stack.addWidget(self.build_dependency_form())
        return self.form_stack

    def build_task_form(self):
        widget = QWidget()
        form = QFormLayout(widget)
        self.task_id_edit = QLineEdit()
        self.task_name_edit = QLineEdit()
        self.task_status_combo = QComboBox()
        self.task_status_combo.addItems(STATUS_OPTIONS)
        self.task_group_combo = QComboBox()
        self.task_group_combo.setEditable(True)
        self.task_link_edit = QLineEdit()
        self.task_inputs_edit = QLineEdit()
        self.task_outputs_edit = QLineEdit()
        self.task_resources_edit = QLineEdit()
        self.task_x_spin = self.make_position_spinbox()
        self.task_y_spin = self.make_position_spinbox()

        form.addRow("ID", self.task_id_edit)
        form.addRow("Name", self.task_name_edit)
        form.addRow("Status", self.task_status_combo)
        form.addRow("Group", self.task_group_combo)
        form.addRow("Link", self.with_link_buttons(self.task_link_edit))
        form.addRow("Inputs", self.task_inputs_edit)
        form.addRow("Outputs", self.task_outputs_edit)
        form.addRow("Resources", self.task_resources_edit)
        form.addRow("X", self.task_x_spin)
        form.addRow("Y", self.task_y_spin)

        for widget_to_watch in (
            self.task_id_edit,
            self.task_name_edit,
            self.task_link_edit,
            self.task_inputs_edit,
            self.task_outputs_edit,
            self.task_resources_edit,
        ):
            widget_to_watch.editingFinished.connect(self.apply_task_form)
        self.task_status_combo.currentTextChanged.connect(self.apply_task_form)
        self.task_group_combo.currentTextChanged.connect(self.apply_task_form)
        self.task_x_spin.valueChanged.connect(self.apply_task_form)
        self.task_y_spin.valueChanged.connect(self.apply_task_form)
        return widget

    def build_artifact_form(self):
        widget = QWidget()
        form = QFormLayout(widget)
        self.artifact_id_edit = QLineEdit()
        self.artifact_name_edit = QLineEdit()
        self.artifact_kind_combo = QComboBox()
        self.artifact_kind_combo.addItems(ARTIFACT_KIND_OPTIONS)
        self.artifact_link_edit = QLineEdit()

        form.addRow("ID", self.artifact_id_edit)
        form.addRow("Name", self.artifact_name_edit)
        form.addRow("Kind", self.artifact_kind_combo)
        form.addRow("Link", self.with_link_buttons(self.artifact_link_edit))

        self.artifact_id_edit.editingFinished.connect(self.apply_artifact_form)
        self.artifact_name_edit.editingFinished.connect(self.apply_artifact_form)
        self.artifact_link_edit.editingFinished.connect(self.apply_artifact_form)
        self.artifact_kind_combo.currentTextChanged.connect(self.apply_artifact_form)
        return widget

    def build_dependency_form(self):
        widget = QWidget()
        form = QFormLayout(widget)
        self.dep_from_combo = QComboBox()
        self.dep_to_combo = QComboBox()
        form.addRow("From", self.dep_from_combo)
        form.addRow("To", self.dep_to_combo)
        self.dep_from_combo.currentTextChanged.connect(self.apply_dependency_form)
        self.dep_to_combo.currentTextChanged.connect(self.apply_dependency_form)
        return widget

    def make_position_spinbox(self):
        spinbox = QDoubleSpinBox()
        spinbox.setRange(-100000, 100000)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(10)
        return spinbox

    def with_link_buttons(self, line_edit):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        file_button = QPushButton("File")
        folder_button = QPushButton("Folder")
        file_button.clicked.connect(lambda: self.pick_file_for(line_edit))
        folder_button.clicked.connect(lambda: self.pick_folder_for(line_edit))
        layout.addWidget(file_button)
        layout.addWidget(folder_button)
        return widget

    def pick_file_for(self, line_edit):
        filename, _ = QFileDialog.getOpenFileName(self, "ファイルを選択")
        if filename:
            line_edit.setText(filename)
            line_edit.editingFinished.emit()

    def pick_folder_for(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            line_edit.setText(folder)
            line_edit.editingFinished.emit()

    def set_modified(self, modified=True):
        self.modified = modified
        marker = "*" if modified else ""
        filename = self.current_file.name if self.current_file else "TaskFlow"
        self.setWindowTitle(f"{filename}{marker}")

    def mark_editor_modified(self, rebuild_graph=False):
        if rebuild_graph:
            self.refresh_graph_view()
        self.refresh_editor()
        self.set_modified(True)

    def id_list_to_text(self, values) -> str:
        return ", ".join(normalize_id_list(values))

    def text_to_id_list(self, text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def group_names(self) -> list[str]:
        return sorted({task_group(task) for task in self.project.get("tasks", []) if task_group(task)})

    def next_id(self, prefix: str, existing_ids) -> str:
        used = {str(item_id) for item_id in existing_ids}
        index = 1
        while True:
            candidate = f"{prefix}{index:02d}"
            if candidate not in used:
                return candidate
            index += 1

    def find_task(self, task_id: str):
        for task in self.project.get("tasks", []):
            if str(task.get("id")) == task_id:
                return task
        return None

    def find_artifact(self, artifact_id: str):
        for artifact in self.project.get("artifacts", []):
            if str(artifact.get("id")) == artifact_id:
                return artifact
        return None

    def find_dependency(self, index: int):
        dependencies = self.project.get("dependencies", [])
        if 0 <= index < len(dependencies):
            return dependencies[index]
        return None

    def refresh_editor(self):
        if not hasattr(self, "task_list"):
            return

        current_kind = self.selected_kind
        current_id = self.selected_id
        current_dep_row = current_id if current_kind == "dependency" else None
        self._updating_editor = True
        try:
            self.task_list.clear()
            sorted_tasks = sorted(
                self.project.get("tasks", []),
                key=lambda task: (task_group(task) or "~~~", str(task.get("id", ""))),
            )
            for task in sorted_tasks:
                task_id = str(task.get("id", ""))
                group = task_group(task)
                label = f"{group} / {task_id}  {task.get('name', '')}" if group else f"未分類 / {task_id}  {task.get('name', '')}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, task_id)
                self.task_list.addItem(item)
                if current_kind == "task" and task_id == current_id:
                    self.task_list.setCurrentItem(item)

            self.artifact_list.clear()
            for artifact in self.project.get("artifacts", []):
                artifact_id = str(artifact.get("id", ""))
                item = QListWidgetItem(artifact_label(artifact))
                item.setData(Qt.UserRole, artifact_id)
                self.artifact_list.addItem(item)
                if current_kind == "artifact" and artifact_id == current_id:
                    self.artifact_list.setCurrentItem(item)

            self.dependency_list.clear()
            for index, dep in enumerate(self.project.get("dependencies", [])):
                item = QListWidgetItem(f"{dep.get('from', '')} -> {dep.get('to', '')}")
                item.setData(Qt.UserRole, index)
                self.dependency_list.addItem(item)
                if current_kind == "dependency" and index == current_dep_row:
                    self.dependency_list.setCurrentItem(item)

            task_ids = [str(task.get("id", "")) for task in self.project.get("tasks", []) if task.get("id")]
            self.dep_from_combo.clear()
            self.dep_to_combo.clear()
            self.dep_from_combo.addItems(task_ids)
            self.dep_to_combo.addItems(task_ids)
            current_group = self.task_group_combo.currentText()
            self.task_group_combo.clear()
            self.task_group_combo.addItem("")
            self.task_group_combo.addItems(self.group_names())
            self.task_group_combo.setCurrentText(current_group)
            self.populate_selected_form()
            self.update_json_preview()
        finally:
            self._updating_editor = False

    def update_json_preview(self):
        self.sync_positions()
        self.json_preview.setPlainText(json.dumps(self.project, ensure_ascii=False, indent=2))

    def populate_selected_form(self):
        if self.selected_kind == "task":
            self.populate_task_form()
        elif self.selected_kind == "artifact":
            self.populate_artifact_form()
        elif self.selected_kind == "dependency":
            self.populate_dependency_form()
        else:
            self.form_stack.setCurrentIndex(0)

    def populate_task_form(self):
        task = self.find_task(str(self.selected_id))
        if not task:
            self.form_stack.setCurrentIndex(0)
            return
        self.form_stack.setCurrentIndex(1)
        self.task_id_edit.setText(str(task.get("id", "")))
        self.task_name_edit.setText(str(task.get("name", "")))
        status = str(task.get("status", STATUS_OPTIONS[0]))
        self.task_status_combo.setCurrentText(status if status in STATUS_OPTIONS else STATUS_OPTIONS[0])
        self.task_group_combo.setCurrentText(task_group(task))
        self.task_link_edit.setText(str(get_task_link(task)))
        self.task_inputs_edit.setText(self.id_list_to_text(task.get("inputs")))
        self.task_outputs_edit.setText(self.id_list_to_text(task.get("outputs")))
        self.task_resources_edit.setText(self.id_list_to_text(task.get("resources")))
        self.task_x_spin.setValue(float(task.get("x", 0)))
        self.task_y_spin.setValue(float(task.get("y", 0)))

    def populate_artifact_form(self):
        artifact = self.find_artifact(str(self.selected_id))
        if not artifact:
            self.form_stack.setCurrentIndex(0)
            return
        self.form_stack.setCurrentIndex(2)
        self.artifact_id_edit.setText(str(artifact.get("id", "")))
        self.artifact_name_edit.setText(str(artifact.get("name", "")))
        self.artifact_kind_combo.setCurrentText(str(artifact.get("kind", "artifact")))
        self.artifact_link_edit.setText(str(get_artifact_link(artifact)))

    def populate_dependency_form(self):
        dep = self.find_dependency(int(self.selected_id))
        if not dep:
            self.form_stack.setCurrentIndex(0)
            return
        self.form_stack.setCurrentIndex(3)
        self.dep_from_combo.setCurrentText(str(dep.get("from", "")))
        self.dep_to_combo.setCurrentText(str(dep.get("to", "")))

    def select_editor_item(self, kind: str, item):
        if self._updating_editor or item is None:
            return
        self.selected_kind = kind
        self.selected_id = item.data(Qt.UserRole)
        if kind == "task":
            self.project_tabs.setCurrentWidget(self.task_list)
        elif kind == "artifact":
            self.project_tabs.setCurrentWidget(self.artifact_list)
        elif kind == "dependency":
            self.project_tabs.setCurrentWidget(self.dependency_list)
        self.refresh_editor()

    def on_task_item_selected(self, current, previous):
        self.select_editor_item("task", current)

    def on_artifact_item_selected(self, current, previous):
        self.select_editor_item("artifact", current)

    def on_dependency_item_selected(self, current, previous):
        self.select_editor_item("dependency", current)

    def add_selected_tab_item(self):
        current = self.project_tabs.currentWidget()
        if current is self.task_list:
            self.add_task()
        elif current is self.artifact_list:
            self.add_artifact()
        else:
            self.add_dependency()

    def add_task(self):
        task_id = self.next_id("T", self.tasks.keys())
        task = {
            "id": task_id,
            "name": "New Task",
            "status": STATUS_OPTIONS[0],
            "group": "",
            "link": "",
            "inputs": [],
            "outputs": [],
            "resources": [],
            "x": len(self.project.get("tasks", [])) * 40,
            "y": len(self.project.get("tasks", [])) * 40,
        }
        self.project.setdefault("tasks", []).append(task)
        self.selected_kind = "task"
        self.selected_id = task_id
        self.mark_editor_modified(rebuild_graph=True)

    def add_artifact(self):
        artifact_id = self.next_id("A", [artifact.get("id") for artifact in self.project.get("artifacts", [])])
        artifact = {"id": artifact_id, "name": "New Artifact", "kind": "artifact", "link": ""}
        self.project.setdefault("artifacts", []).append(artifact)
        self.selected_kind = "artifact"
        self.selected_id = artifact_id
        self.mark_editor_modified()

    def add_dependency(self):
        task_ids = [str(task.get("id")) for task in self.project.get("tasks", []) if task.get("id")]
        if len(task_ids) < 2:
            QMessageBox.information(self, "依存関係を追加できません", "依存関係にはタスクが2つ以上必要です")
            return
        dep = None
        existing = {(item.get("from"), item.get("to")) for item in self.project.get("dependencies", [])}
        for source in task_ids:
            for target in task_ids:
                if source == target or (source, target) in existing:
                    continue
                candidate = {"from": source, "to": target}
                self.project.setdefault("dependencies", []).append(candidate)
                if not self.has_cycle():
                    dep = candidate
                    break
                self.project["dependencies"].pop()
            if dep:
                break
        if not dep:
            QMessageBox.information(self, "依存関係を追加できません", "追加できる依存関係の組み合わせがありません")
            return
        self.selected_kind = "dependency"
        self.selected_id = len(self.project["dependencies"]) - 1
        self.mark_editor_modified(rebuild_graph=True)

    def delete_selected_item(self):
        if self.selected_kind == "task":
            self.delete_task(str(self.selected_id))
        elif self.selected_kind == "artifact":
            self.delete_artifact(str(self.selected_id))
        elif self.selected_kind == "dependency":
            dependencies = self.project.get("dependencies", [])
            index = int(self.selected_id)
            if 0 <= index < len(dependencies):
                dependencies.pop(index)
                self.selected_kind = None
                self.selected_id = None
                self.mark_editor_modified(rebuild_graph=True)

    def delete_task(self, task_id: str):
        self.project["tasks"] = [task for task in self.project.get("tasks", []) if str(task.get("id")) != task_id]
        self.project["dependencies"] = [
            dep for dep in self.project.get("dependencies", [])
            if dep.get("from") != task_id and dep.get("to") != task_id
        ]
        self.selected_kind = None
        self.selected_id = None
        self.mark_editor_modified(rebuild_graph=True)

    def delete_artifact(self, artifact_id: str):
        self.project["artifacts"] = [
            artifact for artifact in self.project.get("artifacts", [])
            if str(artifact.get("id")) != artifact_id
        ]
        for task in self.project.get("tasks", []):
            for field in ("inputs", "outputs", "resources"):
                task[field] = [item_id for item_id in normalize_id_list(task.get(field)) if item_id != artifact_id]
        self.selected_kind = None
        self.selected_id = None
        self.mark_editor_modified(rebuild_graph=True)

    def apply_task_form(self):
        if self._updating_editor or self.selected_kind != "task":
            return

        task = self.find_task(str(self.selected_id))
        if not task:
            return

        old_id = str(task.get("id", ""))
        new_id = self.task_id_edit.text().strip()
        if not new_id:
            QMessageBox.warning(self, "IDが空です", "タスクIDを入力してください")
            self.refresh_editor()
            return
        if new_id != old_id and self.find_task(new_id):
            QMessageBox.warning(self, "IDが重複しています", f"{new_id} はすでに使われています")
            self.refresh_editor()
            return

        if new_id != old_id:
            for dep in self.project.get("dependencies", []):
                if dep.get("from") == old_id:
                    dep["from"] = new_id
                if dep.get("to") == old_id:
                    dep["to"] = new_id
            self.selected_id = new_id

        task["id"] = new_id
        task["name"] = self.task_name_edit.text().strip()
        task["status"] = self.task_status_combo.currentText()
        group = self.task_group_combo.currentText().strip()
        if group:
            task["group"] = group
        else:
            task.pop("group", None)
        task["link"] = self.task_link_edit.text().strip()
        task["inputs"] = self.text_to_id_list(self.task_inputs_edit.text())
        task["outputs"] = self.text_to_id_list(self.task_outputs_edit.text())
        task["resources"] = self.text_to_id_list(self.task_resources_edit.text())
        task["x"] = self.task_x_spin.value()
        task["y"] = self.task_y_spin.value()
        self.mark_editor_modified(rebuild_graph=True)

    def apply_artifact_form(self):
        if self._updating_editor or self.selected_kind != "artifact":
            return

        artifact = self.find_artifact(str(self.selected_id))
        if not artifact:
            return

        old_id = str(artifact.get("id", ""))
        new_id = self.artifact_id_edit.text().strip()
        if not new_id:
            QMessageBox.warning(self, "IDが空です", "成果物IDを入力してください")
            self.refresh_editor()
            return
        if new_id != old_id and self.find_artifact(new_id):
            QMessageBox.warning(self, "IDが重複しています", f"{new_id} はすでに使われています")
            self.refresh_editor()
            return

        if new_id != old_id:
            for task in self.project.get("tasks", []):
                for field in ("inputs", "outputs", "resources"):
                    task[field] = [new_id if item_id == old_id else item_id for item_id in normalize_id_list(task.get(field))]
            self.selected_id = new_id

        artifact["id"] = new_id
        artifact["name"] = self.artifact_name_edit.text().strip()
        artifact["kind"] = self.artifact_kind_combo.currentText()
        artifact["link"] = self.artifact_link_edit.text().strip()
        self.mark_editor_modified(rebuild_graph=True)

    def apply_dependency_form(self):
        if self._updating_editor or self.selected_kind != "dependency":
            return

        dep = self.find_dependency(int(self.selected_id))
        if not dep:
            return

        source = self.dep_from_combo.currentText()
        target = self.dep_to_combo.currentText()
        if not source or not target:
            return
        if source == target:
            QMessageBox.warning(self, "依存関係が不正です", "同じタスク同士は接続できません")
            self.refresh_editor()
            return

        old_from = dep.get("from")
        old_to = dep.get("to")
        dep["from"] = source
        dep["to"] = target
        if self.has_duplicate_dependency() or self.has_cycle():
            dep["from"] = old_from
            dep["to"] = old_to
            QMessageBox.warning(self, "依存関係が不正です", "重複または循環する依存関係は保存できません")
            self.refresh_editor()
            return

        self.mark_editor_modified(rebuild_graph=True)

    def has_duplicate_dependency(self) -> bool:
        seen = set()
        for dep in self.project.get("dependencies", []):
            pair = (dep.get("from"), dep.get("to"))
            if pair in seen:
                return True
            seen.add(pair)
        return False

    def has_cycle(self) -> bool:
        task_ids = [str(task.get("id")) for task in self.project.get("tasks", []) if task.get("id")]
        successors = {task_id: [] for task_id in task_ids}
        indegree = {task_id: 0 for task_id in task_ids}
        for dep in self.project.get("dependencies", []):
            source = dep.get("from")
            target = dep.get("to")
            if source in successors and target in indegree:
                successors[source].append(target)
                indegree[target] += 1

        queue = deque([task_id for task_id, degree in indegree.items() if degree == 0])
        processed = 0
        while queue:
            current = queue.popleft()
            processed += 1
            for target in successors[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        return processed != len(task_ids)

    def new_project(self):
        self.cancel_dependency_pick_mode()
        self.current_file = None
        self.selected_kind = None
        self.selected_id = None
        self.project = {"tasks": [], "artifacts": [], "dependencies": []}
        self.refresh_graph_view()
        self.refresh_editor()
        self.set_modified(False)
        self.statusBar().showMessage("新しいプロジェクトを作成しました", 3000)

    def refresh_graph_view(self):
        self._layout_in_progress = True
        try:
            self.clear_graph()
            self.tasks = {
                str(task.get("id")): task
                for task in self.project.get("tasks", [])
                if task.get("id")
            }
            self.artifacts = {
                str(artifact.get("id")): artifact
                for artifact in self.project.get("artifacts", [])
                if artifact.get("id")
            }

            for task in self.project.get("tasks", []):
                if not task.get("id"):
                    continue
                node = TaskNodeItem(task, self)
                self.scene.addItem(node)
                self.nodes[node.task_id] = node

            for dep in self.project.get("dependencies", []):
                source = self.nodes.get(dep.get("from"))
                target = self.nodes.get(dep.get("to"))
                if source and target:
                    edge = EdgeItem(source, target, dep, self)
                    self.scene.addItem(edge)
                    source.add_edge(edge)
                    target.add_edge(edge)
                    self.edges.append(edge)
        finally:
            self._layout_in_progress = False

        self.update_group_items()
        self.fit_all()

    def clear_group_items(self):
        for item in self.group_items:
            if item.scene() is not None:
                item.scene().removeItem(item)
        self.group_items = []

    def update_group_items(self):
        if not hasattr(self, "scene"):
            return

        self.clear_group_items()
        grouped_nodes = defaultdict(list)
        for node in self.nodes.values():
            group = task_group(node.task)
            if group:
                grouped_nodes[group].append(node)

        for index, group in enumerate(sorted(grouped_nodes)):
            nodes = grouped_nodes[group]
            if not nodes:
                continue

            rect = nodes[0].sceneBoundingRect()
            for node in nodes[1:]:
                rect = rect.united(node.sceneBoundingRect())

            rect = rect.adjusted(-28, -34, 28, 28)
            base_color = QColor(GROUP_COLORS[index % len(GROUP_COLORS)])
            fill_color = QColor(base_color)
            fill_color.setAlpha(70)
            pen_color = QColor(base_color)
            pen_color.setAlpha(210)

            group_rect = QGraphicsRectItem(rect)
            group_rect.setZValue(-3)
            group_rect.setBrush(QBrush(fill_color))
            group_rect.setPen(QPen(pen_color, 1.5, Qt.DashLine))
            self.scene.addItem(group_rect)
            self.group_items.append(group_rect)

            label = QGraphicsTextItem(group)
            label.setDefaultTextColor(QColor("#374151"))
            label.setZValue(-2)
            label.setPos(rect.left() + 8, rect.top() + 4)
            self.scene.addItem(label)
            self.group_items.append(label)

    def clear_graph(self):
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.group_items.clear()
        self.tasks.clear()
        self.artifacts.clear()
        self.expanded_node = None

    def select_task_node(self, node: TaskNodeItem):
        self.selected_kind = "task"
        self.selected_id = node.task_id
        self.refresh_editor()
        self.refresh_dependency_pick_styles()

    def find_dependency_index_for_edge(self, edge: EdgeItem):
        dependencies = self.project.get("dependencies", [])
        for index, dep in enumerate(dependencies):
            if dep is edge.dependency:
                return index
        for index, dep in enumerate(dependencies):
            if dep.get("from") == edge.dependency.get("from") and dep.get("to") == edge.dependency.get("to"):
                return index
        return None

    def select_dependency_edge(self, edge: EdgeItem) -> bool:
        if self.is_dependency_pick_mode:
            return False
        index = self.find_dependency_index_for_edge(edge)
        if index is None:
            return False
        self.scene.clearSelection()
        edge.setSelected(True)
        self.selected_kind = "dependency"
        self.selected_id = index
        self.refresh_editor()
        return True

    def delete_dependency_edge(self, edge: EdgeItem) -> bool:
        index = self.find_dependency_index_for_edge(edge)
        if index is None:
            return False
        dependencies = self.project.get("dependencies", [])
        if not (0 <= index < len(dependencies)):
            return False
        label = edge.label()
        dependencies.pop(index)
        self.selected_kind = None
        self.selected_id = None
        self.mark_editor_modified(rebuild_graph=True)
        self.statusBar().showMessage(f"依存関係を解除しました: {label}", 4000)
        return True

    def task_node_for_item(self, item):
        while item is not None:
            if isinstance(item, TaskNodeItem):
                return item
            item = item.parentItem()
        return None

    def toggle_dependency_pick_mode(self, checked: bool):
        if checked:
            if len(self.nodes) < 2:
                self.add_dependency_action.setChecked(False)
                self.statusBar().showMessage("依存関係を追加するにはタスクが2つ以上必要です", 4000)
                return
            self.is_dependency_pick_mode = True
            self.dependency_source_id = None
            self.statusBar().showMessage("依存元にするタスクをクリックしてください", 6000)
        else:
            self.cancel_dependency_pick_mode()
            return
        self.refresh_dependency_pick_styles()

    def cancel_dependency_pick_mode(self):
        self.is_dependency_pick_mode = False
        self.dependency_source_id = None
        if hasattr(self, "add_dependency_action"):
            self.add_dependency_action.setChecked(False)
        self.refresh_dependency_pick_styles()

    def refresh_dependency_pick_styles(self):
        if not hasattr(self, "nodes"):
            return
        for node in self.nodes.values():
            node.refresh_style()

    def clear_current_selection(self):
        self.scene.clearSelection()
        self.selected_kind = None
        self.selected_id = None
        self.refresh_editor()
        self.refresh_dependency_pick_styles()

    def clear_dependency_source(self):
        self.dependency_source_id = None
        self.refresh_dependency_pick_styles()

    def can_add_dependency_to(self, target_id: str) -> bool:
        source_id = self.dependency_source_id
        if not self.is_dependency_pick_mode or not source_id:
            return False
        if source_id == target_id:
            return False
        if self.dependency_exists(source_id, target_id):
            return False
        return not self.would_create_cycle(source_id, target_id)

    def dependency_exists(self, source_id: str, target_id: str) -> bool:
        return any(
            dep.get("from") == source_id and dep.get("to") == target_id
            for dep in self.project.get("dependencies", [])
        )

    def would_create_cycle(self, source_id: str, target_id: str) -> bool:
        successors = defaultdict(list)
        for dep in self.project.get("dependencies", []):
            source = dep.get("from")
            target = dep.get("to")
            if source and target:
                successors[source].append(target)
        successors[source_id].append(target_id)

        queue = deque([source_id])
        seen = set()
        while queue:
            current = queue.popleft()
            if current == source_id and current in seen:
                return True
            if current in seen:
                continue
            seen.add(current)
            for next_id in successors.get(current, []):
                if next_id == source_id:
                    return True
                queue.append(next_id)
        return False

    def handle_dependency_target_click(self, node: TaskNodeItem) -> bool:
        if not self.is_dependency_pick_mode:
            return False

        source_id = self.dependency_source_id
        target_id = node.task_id
        if source_id is None:
            self.dependency_source_id = target_id
            self.select_task_node(node)
            self.statusBar().showMessage(f"{target_id} を依存元にしました。依存先にするタスクをクリックしてください", 6000)
            return True

        if source_id == target_id:
            self.statusBar().showMessage("同じタスク同士は依存関係にできません", 4000)
            return True
        if self.dependency_exists(source_id, target_id):
            self.statusBar().showMessage(f"{source_id} -> {target_id} は既に存在します", 4000)
            return True
        if self.would_create_cycle(source_id, target_id):
            self.statusBar().showMessage(f"{source_id} -> {target_id} は循環依存になるため追加できません", 5000)
            return True

        dep = {"from": source_id, "to": target_id}
        self.project.setdefault("dependencies", []).append(dep)
        self.selected_kind = "dependency"
        self.selected_id = len(self.project["dependencies"]) - 1
        self.clear_dependency_source()
        self.mark_editor_modified(rebuild_graph=True)
        self.refresh_dependency_pick_styles()
        self.statusBar().showMessage(f"依存関係を追加しました: {source_id} -> {target_id}。続けて依存元をクリックできます", 5000)
        return True

    def handle_canvas_empty_click(self) -> bool:
        handled = False
        if self.is_dependency_pick_mode and self.dependency_source_id is not None:
            self.clear_dependency_source()
            self.statusBar().showMessage("依存元の選択を解除しました。依存元にするタスクをクリックしてください", 4000)
            handled = True

        if self.selected_kind is not None or self.scene.selectedItems():
            self.clear_current_selection()
            handled = True

        return handled or self.is_dependency_pick_mode

    def toggle_task_node(self, node: TaskNodeItem):
        if node.expanded:
            node.set_expanded(False)
            self.expanded_node = None
            self.select_task_node(node)
            self.update_group_items()
            self.update_json_preview()
            return
        self.expand_task_node(node)

    def expand_task_node(self, node: TaskNodeItem):
        if self.expanded_node is not None and self.expanded_node is not node:
            self.expanded_node.set_expanded(False)
        self.expanded_node = node
        node.set_expanded(True)
        self.select_task_node(node)
        if self.resolve_node_overlaps():
            self.statusBar().showMessage("展開したタスクに合わせて重なりを避けました", 3000)

    def resolve_node_overlaps(self) -> bool:
        """Push lower nodes down when an expanded node would cover them."""
        def overlaps_horizontally(a: QRectF, b: QRectF) -> bool:
            return a.left() < b.right() and a.right() > b.left()

        changed = False
        placed_rects = []
        nodes = sorted(
            self.nodes.values(),
            key=lambda item: (
                item.sceneBoundingRect().top(),
                item.sceneBoundingRect().left(),
                str(item.task_id),
            ),
        )

        self._layout_in_progress = True
        try:
            for node in nodes:
                rect = node.sceneBoundingRect()
                shift_y = 0.0
                for placed_rect in placed_rects:
                    if not overlaps_horizontally(rect.translated(0, shift_y), placed_rect):
                        continue
                    min_top = placed_rect.bottom() + self.NODE_VERTICAL_GAP
                    if rect.top() + shift_y < min_top and rect.bottom() + shift_y > placed_rect.top():
                        shift_y = max(shift_y, min_top - rect.top())

                if shift_y:
                    node.setPos(node.pos().x(), node.pos().y() + shift_y)
                    node.task["x"] = node.pos().x()
                    node.task["y"] = node.pos().y()
                    changed = True
                    rect = node.sceneBoundingRect()

                placed_rects.append(rect)
        finally:
            self._layout_in_progress = False

        if changed:
            for edge in self.edges:
                edge.update_path()
            self.update_group_items()
            self.set_modified(True)

        return changed

    def get_task_artifacts(self, task: dict, field: str) -> list[dict]:
        artifacts = []
        for artifact_id in normalize_id_list(task.get(field)):
            artifact = self.artifacts.get(artifact_id)
            if artifact:
                artifacts.append(artifact)
        return artifacts

    def load_project(self, project: dict):
        self.cancel_dependency_pick_mode()
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
                    edge = EdgeItem(source, target, dep, self)
                    self.scene.addItem(edge)
                    source.add_edge(edge)
                    target.add_edge(edge)
                    self.edges.append(edge)
        finally:
            self._layout_in_progress = False

        self.update_group_items()
        self.fit_all()
        self.refresh_editor()
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
        validation_errors = self.validate_project()
        if validation_errors:
            QMessageBox.warning(self, "保存できません", "\n".join(validation_errors))
            return
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(self.project, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))
            return

        self.set_modified(False)
        self.statusBar().showMessage(f"保存しました: {self.current_file}", 3000)
        self.update_json_preview()

    def validate_project(self) -> list[str]:
        errors = []
        task_ids = {str(task.get("id")) for task in self.project.get("tasks", []) if task.get("id")}
        artifact_ids = {str(artifact.get("id")) for artifact in self.project.get("artifacts", []) if artifact.get("id")}

        if any(not task.get("id") for task in self.project.get("tasks", [])):
            errors.append("IDが空のタスクがあります")
        if any(not artifact.get("id") for artifact in self.project.get("artifacts", [])):
            errors.append("IDが空の成果物があります")
        if len(task_ids) != len([task for task in self.project.get("tasks", []) if task.get("id")]):
            errors.append("タスクIDが重複しています")
        if len(artifact_ids) != len([artifact for artifact in self.project.get("artifacts", []) if artifact.get("id")]):
            errors.append("成果物IDが重複しています")

        for dep in self.project.get("dependencies", []):
            if dep.get("from") not in task_ids or dep.get("to") not in task_ids:
                errors.append("未定義のタスクを使っている依存関係があります")
                break
        if self.has_duplicate_dependency():
            errors.append("依存関係が重複しています")
        if self.has_cycle():
            errors.append("依存関係が循環しています")

        for task in self.project.get("tasks", []):
            for field in ("inputs", "outputs", "resources"):
                unknown = [item_id for item_id in normalize_id_list(task.get(field)) if item_id not in artifact_ids]
                if unknown:
                    errors.append(f"{task.get('id')} の {field} に未定義の成果物があります: {', '.join(unknown)}")

        return errors

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
            self.update_group_items()
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
            self.update_group_items()
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.is_dependency_pick_mode:
            self.cancel_dependency_pick_mode()
            self.statusBar().showMessage("依存関係の追加をキャンセルしました", 3000)
            event.accept()
            return
        if event.key() == Qt.Key_Delete and self.selected_kind == "dependency":
            self.delete_selected_item()
            event.accept()
            return
        super().keyPressEvent(event)


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
