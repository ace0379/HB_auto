# -*- coding: utf-8 -*-
"""PyQt GUI shaped after the legacy auto.ui file."""

from __future__ import annotations

from pathlib import Path
import sys
import traceback

import pandas as pd
from PyQt6 import QtCore, QtGui, QtWidgets

from analysis_tools import (
    average_channel,
    export_average_excel,
    first_type,
    preprocessing,
    second_type,
)
from converter import iad_to_csv


class TimeSeriesPlot(QtWidgets.QWidget):
    range_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series: list[dict] = []
        self.start_s = 0.0
        self.end_s = 0.0
        self.x_min = 0.0
        self.x_max = 1.0
        self.full_x_min = 0.0
        self.full_x_max = 1.0
        self.y_min = 0.0
        self.y_max = 1.0
        self.drag_start_x: float | None = None
        self.pan_start_pixel_x: float | None = None
        self.pan_start_pixel_y: float | None = None
        self.pan_start_range: tuple[float, float] | None = None
        self.pan_start_y_range: tuple[float, float] | None = None
        self.drag_mode: str | None = None
        self.pending_range_start: float | None = None
        self.user_defined_range = False
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)

    def set_series(self, series: list[dict]) -> None:
        self.series = series
        self._fit_bounds()
        if self.end_s <= self.start_s:
            self.start_s = self.x_min
            self.end_s = min(self.x_min + 600.0, self.x_max)
        self.update()

    def clear(self) -> None:
        self.series = []
        self.start_s = 0.0
        self.end_s = 0.0
        self.x_min = 0.0
        self.x_max = 1.0
        self.full_x_min = 0.0
        self.full_x_max = 1.0
        self.y_min = 0.0
        self.y_max = 1.0
        self.drag_start_x = None
        self.pan_start_pixel_x = None
        self.pan_start_pixel_y = None
        self.pan_start_range = None
        self.pan_start_y_range = None
        self.drag_mode = None
        self.pending_range_start = None
        self.user_defined_range = False
        self.update()

    def set_range(self, start_s: float, end_s: float) -> None:
        self.start_s = min(start_s, end_s)
        self.end_s = max(start_s, end_s)
        self.update()

    def set_user_defined_range(self, enabled: bool) -> None:
        self.user_defined_range = enabled
        self.pending_range_start = None


    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QtGui.QColor("white"))
        border_pen = QtGui.QPen(QtGui.QColor(0, 60, 220), 3)
        painter.setPen(border_pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

        plot_rect = self._plot_rect()
        painter.setPen(QtGui.QPen(QtGui.QColor(210, 210, 210), 1))
        painter.drawRect(plot_rect)

        if not self.series:
            painter.setPen(QtGui.QColor(120, 120, 120))
            painter.drawText(plot_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "Select channels and press >")
            painter.end()
            return

        self._draw_grid(painter, plot_rect)
        colors = [
            QtGui.QColor(220, 40, 40),
            QtGui.QColor(40, 120, 220),
            QtGui.QColor(30, 150, 80),
            QtGui.QColor(180, 90, 200),
            QtGui.QColor(230, 140, 20),
        ]

        painter.save()
        painter.setClipRect(plot_rect)
        for index, item in enumerate(self.series):
            painter.setPen(QtGui.QPen(colors[index % len(colors)], 1.6))
            self._draw_series(painter, plot_rect, item["x"], item["y"])
        painter.restore()

        self._draw_average_region(painter, plot_rect)
        self._draw_legend(painter, colors)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if not self.series:
            return

        if event.button() == QtCore.Qt.MouseButton.RightButton or (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
        ):
            self.drag_mode = "range"
            self.drag_start_x = self._pixel_to_x(event.position().x())
            self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        elif event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.drag_mode = "pan"
            self.pan_start_pixel_x = event.position().x()
            self.pan_start_pixel_y = event.position().y()
            self.pan_start_range = (self.x_min, self.x_max)
            self.pan_start_y_range = (self.y_min, self.y_max)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_mode == "range" and self.drag_start_x is not None and self.series:
            current = self._pixel_to_x(event.position().x())
            self.set_range(self.drag_start_x, current)
        elif (
            self.drag_mode == "pan"
            and self.pan_start_pixel_x is not None
            and self.pan_start_pixel_y is not None
            and self.pan_start_range is not None
            and self.pan_start_y_range is not None
            and self.series
        ):
            plot_rect = self._plot_rect()
            pixel_delta_x = event.position().x() - self.pan_start_pixel_x
            pixel_delta_y = event.position().y() - self.pan_start_pixel_y
            time_delta = pixel_delta_x / plot_rect.width() * (self.pan_start_range[1] - self.pan_start_range[0])
            value_delta = pixel_delta_y / plot_rect.height() * (self.pan_start_y_range[1] - self.pan_start_y_range[0])
            self._set_view_range(
                self.pan_start_range[0] - time_delta,
                self.pan_start_range[1] - time_delta,
                self.pan_start_y_range[0] + value_delta,
                self.pan_start_y_range[1] + value_delta,
            )

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_mode == "range" and self.drag_start_x is not None and self.series:
            current = self._pixel_to_x(event.position().x())
            start = max(self.x_min, min(self.drag_start_x, current))
            end = min(self.x_max, max(self.drag_start_x, current))
            self.set_range(start, end)
            self.range_changed.emit(round(start, 1), round(end, 1))
        self.drag_start_x = None
        self.pan_start_pixel_x = None
        self.pan_start_pixel_y = None
        self.pan_start_range = None
        self.pan_start_y_range = None
        self.drag_mode = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.series or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        clicked_x = self._pixel_to_x(event.position().x())
        if not self.user_defined_range:
            self.pending_range_start = None
            self.set_range(clicked_x, clicked_x)
            self.range_changed.emit(round(clicked_x, 1), round(clicked_x, 1))
            return

        if self.pending_range_start is None:
            self.pending_range_start = clicked_x
            self.set_range(clicked_x, clicked_x)
        else:
            start = min(self.pending_range_start, clicked_x)
            end = max(self.pending_range_start, clicked_x)
            self.pending_range_start = None
            self.set_range(start, end)
            self.range_changed.emit(round(start, 1), round(end, 1))

    def wheelEvent(self, event) -> None:
        if not self.series:
            return

        cursor_x = self._pixel_to_x(event.position().x())
        current_width = self.x_max - self.x_min
        zoom_factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        new_width = current_width * zoom_factor
        full_width = self.full_x_max - self.full_x_min
        min_width = max(full_width / 1000.0, 0.1)
        new_width = max(min_width, min(full_width, new_width))

        left_ratio = (cursor_x - self.x_min) / current_width
        new_min = cursor_x - new_width * left_ratio
        new_max = new_min + new_width
        self._set_view_range(new_min, new_max)
        event.accept()

    def _fit_bounds(self) -> None:
        xs = []
        ys = []
        for item in self.series:
            xs.extend(item["x"])
            ys.extend([value for value in item["y"] if pd.notna(value)])

        if xs:
            self.full_x_min = float(min(xs))
            self.full_x_max = float(max(xs))
            self.x_min = self.full_x_min
            self.x_max = self.full_x_max
        if ys:
            self.y_min = float(min(ys))
            self.y_max = float(max(ys))

        if self.x_max <= self.x_min:
            self.x_max = self.x_min + 1.0
        if self.full_x_max <= self.full_x_min:
            self.full_x_max = self.full_x_min + 1.0
        if self.y_max <= self.y_min:
            self.y_max = self.y_min + 1.0

    def _set_view_range(
        self,
        start: float,
        end: float,
        y_start: float | None = None,
        y_end: float | None = None,
    ) -> None:
        width = end - start
        full_width = self.full_x_max - self.full_x_min

        if width >= full_width:
            self.x_min = self.full_x_min
            self.x_max = self.full_x_max
        else:
            if start < self.full_x_min:
                start = self.full_x_min
                end = start + width
            if end > self.full_x_max:
                end = self.full_x_max
                start = end - width
            self.x_min = start
            self.x_max = end

        if y_start is not None and y_end is not None and y_end > y_start:
            self.y_min = y_start
            self.y_max = y_end
        self.update()

    def _plot_rect(self) -> QtCore.QRectF:
        return QtCore.QRectF(45, 20, max(10, self.width() - 65), max(10, self.height() - 50))

    def _draw_grid(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        painter.setPen(QtGui.QPen(QtGui.QColor(235, 235, 235), 1))
        for i in range(1, 5):
            x = rect.left() + rect.width() * i / 5
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))

        painter.setPen(QtGui.QColor(90, 90, 90))
        painter.drawText(4, int(rect.top()) + 12, f"{self.y_max:.1f}")
        painter.drawText(4, int(rect.bottom()), f"{self.y_min:.1f}")
        painter.drawText(int(rect.left()), self.height() - 8, f"{self.x_min:.1f}s")
        painter.drawText(int(rect.right()) - 55, self.height() - 8, f"{self.x_max:.1f}s")

    def _draw_series(self, painter: QtGui.QPainter, rect: QtCore.QRectF, x_values, y_values) -> None:
        segment = []
        step = max(1, len(x_values) // 1200)
        max_draw_gap = self._max_draw_gap(x_values, step)
        previous_x: float | None = None

        for x, y in zip(x_values[::step], y_values[::step]):
            if pd.isna(x) or pd.isna(y):
                if len(segment) >= 2:
                    painter.drawPolyline(segment)
                segment = []
                previous_x = None
                continue

            x_float = float(x)
            if previous_x is not None and max_draw_gap is not None and x_float - previous_x > max_draw_gap:
                if len(segment) >= 2:
                    painter.drawPolyline(segment)
                segment = []

            segment.append(QtCore.QPointF(self._x_to_pixel(x_float, rect), self._y_to_pixel(float(y), rect)))
            previous_x = x_float

        if len(segment) >= 2:
            painter.drawPolyline(segment)

    def _max_draw_gap(self, x_values, draw_step: int) -> float | None:
        x_series = pd.Series(x_values).dropna()
        diffs = x_series.diff().dropna()
        diffs = diffs[diffs > 0]
        if diffs.empty:
            return None
        normal_step = float(diffs.median())
        return normal_step * max(draw_step + 0.5, 1.5)

    def _draw_average_region(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        start_px = self._x_to_pixel(self.start_s, rect)
        end_px = self._x_to_pixel(self.end_s, rect)
        region = QtCore.QRectF(min(start_px, end_px), rect.top(), abs(end_px - start_px), rect.height())
        painter.fillRect(region, QtGui.QColor(255, 230, 230, 80))
        painter.setPen(QtGui.QPen(QtGui.QColor(220, 0, 0), 2))
        painter.drawLine(QtCore.QPointF(start_px, rect.top()), QtCore.QPointF(start_px, rect.bottom()))
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 80, 220), 2))
        painter.drawLine(QtCore.QPointF(end_px, rect.top()), QtCore.QPointF(end_px, rect.bottom()))

    def _draw_legend(self, painter: QtGui.QPainter, colors: list[QtGui.QColor]) -> None:
        x = 55
        y = 16
        for index, item in enumerate(self.series[:5]):
            painter.setPen(QtGui.QPen(colors[index % len(colors)], 2))
            painter.drawLine(x, y - 4, x + 16, y - 4)
            painter.setPen(QtGui.QColor(40, 40, 40))
            painter.drawText(x + 20, y, item["name"][:24])
            x += 115

    def _x_to_pixel(self, value: float, rect: QtCore.QRectF) -> float:
        return rect.left() + (value - self.x_min) / (self.x_max - self.x_min) * rect.width()

    def _y_to_pixel(self, value: float, rect: QtCore.QRectF) -> float:
        return rect.bottom() - (value - self.y_min) / (self.y_max - self.y_min) * rect.height()

    def _pixel_to_x(self, pixel_x: float) -> float:
        rect = self._plot_rect()
        ratio = (pixel_x - rect.left()) / rect.width()
        ratio = max(0.0, min(1.0, ratio))
        return self.x_min + ratio * (self.x_max - self.x_min)


class ImportWorker(QtCore.QThread):
    finished_ok = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, input_path: Path, output_dir: Path, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            suffix = self.input_path.suffix.lower()
            if suffix == ".iad":
                result_path = iad_to_csv(
                    iad_path=self.input_path,
                    work_dir=self.output_dir / "_extracted" / self.input_path.stem,
                    csv_dir=self.output_dir,
                )
            elif suffix == ".csv":
                read_csv_with_fallback(self.input_path, nrows=5, low_memory=False)
                result_path = self.input_path
            else:
                raise ValueError("Only .iad and .csv files are supported.")

            self.finished_ok.emit(str(result_path))
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.failed.emit(detail)


class PreviewDialog(QtWidgets.QDialog):
    def __init__(
        self,
        header_df: pd.DataFrame,
        sub_df: pd.DataFrame,
        main_df: pd.DataFrame,
        start_s: float,
        end_s: float,
        source_file: Path | None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.resize(430, 620)

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(self._comment_text(start_s, end_s, source_file))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Channel", "Avg", "Avg-Amb"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        close_button = QtWidgets.QPushButton("Close", self)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self._load_rows(header_df, sub_df, main_df)

    def _load_rows(self, header_df: pd.DataFrame, sub_df: pd.DataFrame, main_df: pd.DataFrame) -> None:
        rows = []
        top_count = 0
        for df in (header_df, sub_df):
            for _, row in df.iterrows():
                rows.append([_cell_text(row, 0), _cell_text(row, 1), _cell_text(row, 2)])
                top_count += 1
        for _, row in main_df.iterrows():
            rows.append([_cell_text(row, 0), _cell_text(row, 1), _cell_text(row, 2)])

        self.table.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            for column_index, value in enumerate(row_values):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(value))
            if row_index < top_count:
                self.table.setSpan(row_index, 1, 1, 2)

        self.table.resizeColumnsToContents()

    def _comment_text(self, start_s: float, end_s: float, source_file: Path | None) -> str:
        lines = [
            f"Averaging time: {min(start_s, end_s)} ~ {max(start_s, end_s)}",
        ]
        if source_file:
            lines.append(f"Source file: {source_file.name}")
        return "\n".join(lines)



def _detect_measurement_header_row(path: Path, encoding: str, limit: int = 200) -> int | None:
    with path.open("r", encoding=encoding, newline="") as handle:
        for row_index, line in enumerate(handle):
            if row_index >= limit:
                break
            if ".X" in line and "," in line:
                return row_index
    return None


def read_csv_with_fallback(path: Path, **kwargs) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "latin1"):
        try:
            read_kwargs = dict(kwargs)
            if read_kwargs.get("header") is None and "skiprows" not in read_kwargs:
                header_row = _detect_measurement_header_row(path, encoding)
                if header_row is not None:
                    read_kwargs["skiprows"] = header_row
            return pd.read_csv(path, encoding=encoding, **read_kwargs)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return pd.read_csv(path, **kwargs)

def _cell_text(row: pd.Series, index: int) -> str:
    if index >= len(row):
        return ""
    value = row.iloc[index]
    if pd.isna(value):
        return ""
    return str(value)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: ImportWorker | None = None
        self.import_progress: QtWidgets.QProgressDialog | None = None
        self.result_path: Path | None = None
        self.input_path: Path | None = None
        self.df = pd.DataFrame()
        self.grouped_ones = pd.DataFrame()
        self.grouped_tens = pd.DataFrame()
        self.grouped_hundreds = pd.DataFrame()
        self.fuel_channel: list[str] = []
        self.RAD_channels: list[str] = []
        self.OC_channels: list[str] = []
        self.CAC_channels: list[str] = []
        self.isPlotted = False
        self.header_df = pd.DataFrame()
        self.average_baseline_s: float | None = None
        self.setup_ui()

    def setup_ui(self) -> None:
        self.setObjectName("MainWindow")
        self.setWindowTitle("MainWindow")
        self.resize(900, 880)

        self.centralwidget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.centralwidget)

        self.lineEdit_Files = QtWidgets.QLineEdit(self.centralwidget)
        self.lineEdit_Files.setGeometry(QtCore.QRect(130, 20, 190, 20))

        self.pushButton_Files = QtWidgets.QPushButton("...", self.centralwidget)
        self.pushButton_Files.setGeometry(QtCore.QRect(322, 18, 25, 25))

        self.pushButton_Files_import = QtWidgets.QPushButton("Import...", self.centralwidget)
        self.pushButton_Files_import.setGeometry(QtCore.QRect(350, 18, 58, 25))

        self.label_File_location = QtWidgets.QLabel("File location", self.centralwidget)
        self.label_File_location.setGeometry(QtCore.QRect(20, 20, 90, 15))

        labels = [
            ("Test number :", 50),
            ("Test date :", 70),
            ("Test model :", 90),
            ("Test Condition :", 110),
            ("1st fan speed", 130),
            ("2nd fan speed", 150),
            ("A/C status :", 170),
            ("Ambient temp. :", 190),
        ]
        self.info_edits: list[QtWidgets.QWidget] = []
        self.fan_label_edits: list[QtWidgets.QLineEdit] = []
        for index, (text, y) in enumerate(labels):
            if index in (4, 5):
                label = QtWidgets.QLineEdit(text, self.centralwidget)
                label.setGeometry(QtCore.QRect(20, y, 105, 20))
                self.fan_label_edits.append(label)
            else:
                label = QtWidgets.QLabel(text, self.centralwidget)
                label.setGeometry(QtCore.QRect(20, y, 110, 15))

            if index == 1:
                edit = QtWidgets.QDateEdit(self.centralwidget)
                edit.setGeometry(QtCore.QRect(130, y, 160, 20))
                edit.setCalendarPopup(True)
                edit.setDisplayFormat("yyyy-MM-dd")
                edit.setDate(QtCore.QDate.currentDate())
            else:
                edit = QtWidgets.QLineEdit(self.centralwidget)
                edit.setGeometry(QtCore.QRect(130, y, 160, 20))
                if index == 7:
                    validator = QtGui.QDoubleValidator(-9999.0, 9999.0, 3, edit)
                    validator.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
                    edit.setValidator(validator)
            self.info_edits.append(edit)

        self.pushButton_Files_apply = QtWidgets.QPushButton("Apply...", self.centralwidget)
        self.pushButton_Files_apply.setGeometry(QtCore.QRect(320, 170, 80, 50))

        self.line = QtWidgets.QFrame(self.centralwidget)
        self.line.setGeometry(QtCore.QRect(0, 220, 410, 16))
        self.line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)

        self.line_2 = QtWidgets.QFrame(self.centralwidget)
        self.line_2.setGeometry(QtCore.QRect(400, 0, 20, 230))
        self.line_2.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)

        self.label_Averaging_period = QtWidgets.QLabel("Averaging period", self.centralwidget)
        self.label_Averaging_period.setGeometry(QtCore.QRect(710, 0, 150, 20))

        self.pushButton_Backward = QtWidgets.QPushButton("<<", self.centralwidget)
        self.pushButton_Backward.setGeometry(QtCore.QRect(605, 40, 40, 25))

        self.pushButton_Forward = QtWidgets.QPushButton(">>", self.centralwidget)
        self.pushButton_Forward.setGeometry(QtCore.QRect(660, 40, 40, 25))

        self.radioButton_Ten_min = QtWidgets.QRadioButton("10 minutes (default)", self.centralwidget)
        self.radioButton_Ten_min.setGeometry(QtCore.QRect(710, 20, 170, 18))
        self.radioButton_Ten_min.setChecked(True)
        self.radioButton_Five_min = QtWidgets.QRadioButton("5 minutes", self.centralwidget)
        self.radioButton_Five_min.setGeometry(QtCore.QRect(710, 42, 140, 18))
        self.radioButton_User_defined = QtWidgets.QRadioButton("user-defined", self.centralwidget)
        self.radioButton_User_defined.setGeometry(QtCore.QRect(710, 64, 140, 18))

        self.plotWidget = TimeSeriesPlot(self.centralwidget)
        self.plotWidget.setGeometry(QtCore.QRect(460, 110, 420, 315))
        self.plotWidget.range_changed.connect(self._plot_range_changed)

        self.label_Sampling_channels = QtWidgets.QLabel("Sampling channels", self.centralwidget)
        self.label_Sampling_channels.setGeometry(QtCore.QRect(10, 240, 151, 16))
        self.listView_Sampling_channels = QtWidgets.QListWidget(self.centralwidget)
        self.listView_Sampling_channels.setGeometry(QtCore.QRect(10, 270, 330, 150))
        self.listView_Sampling_channels.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.pushButton_Graph = QtWidgets.QPushButton(">", self.centralwidget)
        self.pushButton_Graph.setGeometry(QtCore.QRect(360, 290, 80, 100))

        self.line_3 = QtWidgets.QFrame(self.centralwidget)
        self.line_3.setGeometry(QtCore.QRect(0, 440, 900, 16))
        self.line_3.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.line_3.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)

        self.label_Recording_channels = QtWidgets.QLabel("Recording channels", self.centralwidget)
        self.label_Recording_channels.setGeometry(QtCore.QRect(10, 460, 150, 20))
        self.listView_Recording_channels = QtWidgets.QListWidget(self.centralwidget)
        self.listView_Recording_channels.setGeometry(QtCore.QRect(10, 490, 330, 350))
        self.listView_Recording_channels.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.pushButton_Add = QtWidgets.QPushButton(">", self.centralwidget)
        self.pushButton_Add.setGeometry(QtCore.QRect(360, 560, 80, 50))
        self.pushButton_Remove = QtWidgets.QPushButton("<", self.centralwidget)
        self.pushButton_Remove.setGeometry(QtCore.QRect(360, 630, 80, 50))

        self.comboBox_Specials = QtWidgets.QComboBox(self.centralwidget)
        self.comboBox_Specials.setGeometry(QtCore.QRect(360, 720, 80, 22))
        self.comboBox_Specials.addItems(["fuel rate", "RAD", "OC", "CAC"])
        self.pushButton_Specials_add = QtWidgets.QPushButton(">", self.centralwidget)
        self.pushButton_Specials_add.setGeometry(QtCore.QRect(360, 750, 80, 30))
        self.pushButton_Specials_remove = QtWidgets.QPushButton("<", self.centralwidget)
        self.pushButton_Specials_remove.setGeometry(QtCore.QRect(360, 790, 80, 30))

        self.label_Edit_channel_names = QtWidgets.QLabel("Edit channel names", self.centralwidget)
        self.label_Edit_channel_names.setGeometry(QtCore.QRect(460, 460, 200, 20))
        self.tableWidget_Edit_channels = QtWidgets.QTableWidget(self.centralwidget)
        self.tableWidget_Edit_channels.setGeometry(QtCore.QRect(460, 490, 291, 351))
        self.tableWidget_Edit_channels.setColumnCount(3)
        self.tableWidget_Edit_channels.setRowCount(4)
        self.tableWidget_Edit_channels.setHorizontalHeaderLabels(["Channel", "Avg", "Avg-Amb"])
        for row, text in enumerate(["fuel rate", "RAD \uc804\ub2e8", "OC \uc804\ub2e8", "CAC \uc804\ub2e8"]):
            self.tableWidget_Edit_channels.setItem(row, 0, QtWidgets.QTableWidgetItem(text))

        self.pushButton_Channels_import = QtWidgets.QPushButton("Import...", self.centralwidget)
        self.pushButton_Channels_import.setGeometry(QtCore.QRect(680, 460, 75, 25))
        self.pushButton_Average_updates = QtWidgets.QPushButton("Averaging\nupdates", self.centralwidget)
        self.pushButton_Average_updates.setGeometry(QtCore.QRect(780, 490, 100, 56))
        self.pushButton_Clear_all = QtWidgets.QPushButton("Clear all", self.centralwidget)
        self.pushButton_Clear_all.setGeometry(QtCore.QRect(780, 558, 100, 56))
        self.pushButton_Preview = QtWidgets.QPushButton("Preview...", self.centralwidget)
        self.pushButton_Preview.setGeometry(QtCore.QRect(780, 626, 100, 56))
        self.pushButton_Export = QtWidgets.QPushButton("Export...", self.centralwidget)
        self.pushButton_Export.setGeometry(QtCore.QRect(780, 694, 100, 56))
        self.pushButton_Exit = QtWidgets.QPushButton("\uc804\uccb4\uc885\ub8cc", self.centralwidget)
        self.pushButton_Exit.setGeometry(QtCore.QRect(780, 762, 100, 56))

        self.label_Start_time = QtWidgets.QLabel("Start second", self.centralwidget)
        self.label_Start_time.setGeometry(QtCore.QRect(430, 20, 80, 20))
        self.doubleSpinBox_Start = QtWidgets.QDoubleSpinBox(self.centralwidget)
        self.doubleSpinBox_Start.setGeometry(QtCore.QRect(515, 18, 75, 24))
        self.doubleSpinBox_Start.setDecimals(1)
        self.doubleSpinBox_Start.setMaximum(999999.0)

        self.label_End_time = QtWidgets.QLabel("End second", self.centralwidget)
        self.label_End_time.setGeometry(QtCore.QRect(430, 50, 80, 20))
        self.doubleSpinBox_End = QtWidgets.QDoubleSpinBox(self.centralwidget)
        self.doubleSpinBox_End.setGeometry(QtCore.QRect(515, 48, 75, 24))
        self.doubleSpinBox_End.setDecimals(1)
        self.doubleSpinBox_End.setMaximum(999999.0)

        self.output_dir: Path | None = None
        self.statusbar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

        self.pushButton_Files.clicked.connect(self.load_files)
        self.pushButton_Files_import.clicked.connect(self.import_file)
        self.lineEdit_Files.returnPressed.connect(self.import_file)
        self.pushButton_Files_apply.clicked.connect(self.applying)
        self.pushButton_Graph.clicked.connect(self.plotting)
        self.pushButton_Forward.clicked.connect(self.averaging_forward)
        self.pushButton_Backward.clicked.connect(self.averaging_backward)
        self.pushButton_Add.clicked.connect(self.add_channels)
        self.pushButton_Remove.clicked.connect(self.remove_channels)
        self.pushButton_Specials_add.clicked.connect(self.add_specials)
        self.pushButton_Specials_remove.clicked.connect(self.remove_specials)
        self.pushButton_Average_updates.clicked.connect(self.updating)
        self.pushButton_Clear_all.clicked.connect(self.clearing)
        self.pushButton_Channels_import.clicked.connect(self.import_channel_list)
        self.pushButton_Preview.clicked.connect(self.previewing)
        self.pushButton_Export.clicked.connect(self.output)
        self.pushButton_Exit.clicked.connect(QtWidgets.QApplication.quit)
        self.radioButton_Ten_min.toggled.connect(self._radio_mode_changed)
        self.radioButton_Five_min.toggled.connect(self._radio_mode_changed)
        self.radioButton_User_defined.toggled.connect(self._radio_mode_changed)
        self.doubleSpinBox_Start.valueChanged.connect(self._spin_range_changed)
        self.doubleSpinBox_End.valueChanged.connect(self._spin_range_changed)

    def load_files(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open file",
            "",
            "Data files (*.csv *.iad);;CSV files (*.csv);;IAD files (*.iad)",
        )
        if file_path:
            self.lineEdit_Files.setText(file_path)

    def import_channel_list(self) -> None:
        path_text, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import sensor list",
            str(Path.home()),
            "Excel files (*.xlsx *.xlsm);;CSV files (*.csv);;All files (*.*)",
        )
        if not path_text:
            return

        try:
            channels = self._read_channel_list(Path(path_text))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Import Error", f"Sensor list import failed:\n{exc}")
            return

        if not channels:
            QtWidgets.QMessageBox.warning(self, "Import Error", "No channel names were found in the selected file.")
            return

        self._replace_general_channels(channels)
        self.statusbar.showMessage(f"Sensor list imported. {len(channels)} display names loaded. Select IAD channels and press > to map.")

    def _read_channel_list(self, path: Path) -> list[str]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path, header=None)
        else:
            frame = pd.read_excel(path, header=None)

        if frame.empty:
            return []

        channel_column = self._detect_channel_list_column(frame)
        values = frame.iloc[:, channel_column].dropna()
        channels: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text or text.lower() in {"nan", "sensor list", "channel", "channels"}:
                continue
            if text in {"\uc13c\uc11c\ub9ac\uc2a4\ud2b8", "\ucc44\ub110", "\ucc44\ub110\uba85"}:
                continue
            if text in seen:
                continue
            seen.add(text)
            channels.append(text)
        return channels

    def _detect_channel_list_column(self, frame: pd.DataFrame) -> int:
        for row_index in range(min(len(frame), 10)):
            for column_index, value in enumerate(frame.iloc[row_index]):
                text = str(value).strip().lower()
                if text in {"\uc13c\uc11c\ub9ac\uc2a4\ud2b8", "sensor list", "channel", "channels", "\ucc44\ub110", "\ucc44\ub110\uba85"}:
                    return column_index
        if frame.shape[1] >= 2:
            return 1
        return 0

    def _replace_general_channels(self, channels: list[str]) -> None:
        self.tableWidget_Edit_channels.setRowCount(4 + len(channels))
        for offset, channel_name in enumerate(channels):
            row = 4 + offset
            self.tableWidget_Edit_channels.setItem(row, 0, QtWidgets.QTableWidgetItem(channel_name))
            self.tableWidget_Edit_channels.setItem(row, 1, QtWidgets.QTableWidgetItem(""))
            self.tableWidget_Edit_channels.setItem(row, 2, QtWidgets.QTableWidgetItem(""))

    def import_file(self) -> None:
        path_text = self.lineEdit_Files.text().strip().strip('"')
        if not path_text:
            QtWidgets.QMessageBox.warning(self, "Import Error", "File location is empty.")
            return

        input_path = Path(path_text)
        if not input_path.exists():
            QtWidgets.QMessageBox.critical(self, "Import Error", f"File not found:\n{input_path}")
            return

        self.input_path = input_path
        self.output_dir = input_path.parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._reset_import_state()
        self._set_busy(True)
        self._show_import_progress(input_path)
        self.statusbar.showMessage(f"Importing: {input_path}")

        self.worker = ImportWorker(input_path, self.output_dir, self)
        self.worker.finished_ok.connect(self.import_finished)
        self.worker.failed.connect(self.import_failed)
        self.worker.start()

    def import_finished(self, result_path: str) -> None:
        self.result_path = Path(result_path)
        self.statusbar.showMessage(f"Import completed: {self.result_path}")
        self._load_result_data(self.result_path)
        self._set_busy(False)
        self._hide_import_progress()

    def import_failed(self, message: str) -> None:
        self.statusbar.showMessage("Import failed")
        self._set_busy(False)
        self._hide_import_progress()
        QtWidgets.QMessageBox.critical(self, "Import Error", message)

    def _load_result_data(self, csv_path: Path) -> None:
        try:
            is_iad = bool(self.input_path and self.input_path.suffix.lower() == ".iad")
            raw_df = read_csv_with_fallback(csv_path, header=0 if is_iad else None, low_memory=False)
            self.df = preprocessing(raw_df)
            first_column = str(self.df.columns[0])

            if first_column.endswith(".X"):
                self.grouped_ones, self.grouped_tens, self.grouped_hundreds = first_type(self.df)
            elif first_column.endswith("Hz"):
                self.grouped_ones, self.grouped_tens, self.grouped_hundreds = second_type(self.df)
            else:
                raise ValueError(f"Unknown time column format: {first_column}")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Import Error", f"CSV preprocessing failed:\n{exc}")
            return

        self.populate_channel_lists()

    def populate_channel_lists(self) -> None:
        self.listView_Sampling_channels.clear()
        self.listView_Recording_channels.clear()
        for channel in self._channel_names():
            self.listView_Sampling_channels.addItem(channel)
            self.listView_Recording_channels.addItem(channel)

        max_time = self._max_time()
        self.doubleSpinBox_Start.setRange(0.0, max_time)
        self.doubleSpinBox_End.setRange(0.0, max_time)
        self.doubleSpinBox_Start.setValue(0.0)
        self.doubleSpinBox_End.setValue(min(600.0, max_time))
        self.statusbar.showMessage(f"Import completed. {len(self._channel_names())} channels loaded.")
        self.plotWidget.clear()

    def applying(self) -> None:
        header = [
            ["Test No.", self.info_edits[0].text()],
            ["Test date", self.info_edits[1].text()],
            ["Test model", self.info_edits[2].text()],
            ["Test condition", self.info_edits[3].text()],
            [self.fan_label_edits[0].text().strip() or "1st fan speed", self.info_edits[4].text()],
            [self.fan_label_edits[1].text().strip() or "2nd fan speed", self.info_edits[5].text()],
            ["A/C status", self.info_edits[6].text()],
            ["Ambient temp.", self.info_edits[7].text()],
        ]
        self.header_df = pd.DataFrame(header)
        if not self.df.empty and self.doubleSpinBox_Start.value() != self.doubleSpinBox_End.value():
            self._refresh_average_table()
            self.statusbar.showMessage("Applied header and ambient-corrected averages.")

    def plotting(self) -> None:
        if self.df.empty:
            QtWidgets.QMessageBox.warning(self, "No raw data", "Please import the test data first.")
            return
        selected = [item.text() for item in self.listView_Sampling_channels.selectedItems()]
        if not selected:
            QtWidgets.QMessageBox.warning(self, "No channels", "Please select one or more sampling channels.")
            return

        series = []
        for channel_name in selected:
            item = self._series_for_channel(channel_name)
            if item is not None:
                series.append(item)

        if not series:
            QtWidgets.QMessageBox.warning(self, "No data", "Selected channels do not have plottable data.")
            return

        self.plotWidget.set_series(series)
        self._radio_mode_changed()
        self.plotWidget.set_range(self.doubleSpinBox_Start.value(), self.doubleSpinBox_End.value())
        self.isPlotted = True
        self.statusbar.showMessage(self._plot_help_text())

    def averaging_forward(self) -> None:
        self._apply_period(forward=True)

    def averaging_backward(self) -> None:
        self._apply_period(forward=False)

    def add_channels(self) -> None:
        if not self._check_ready(require_range=True):
            return

        selected = [item.text() for item in self.listView_Recording_channels.selectedItems()]
        if not selected:
            return

        existing = self._existing_mapped_channels()
        mapped_count = 0
        for actual_channel in selected:
            if actual_channel in existing:
                continue

            row = self._first_unmapped_general_row()
            if row is None:
                row = self.tableWidget_Edit_channels.rowCount()
                self.tableWidget_Edit_channels.setRowCount(row + 1)
                self.tableWidget_Edit_channels.setItem(row, 0, QtWidgets.QTableWidgetItem(actual_channel))

            self._set_actual_channel(row, actual_channel)
            self._set_general_average_row(row, self.averaging(actual_channel), self._ambient_temperature())
            existing.add(actual_channel)
            mapped_count += 1

        if mapped_count:
            self.statusbar.showMessage(f"Mapped {mapped_count} IAD channels to display names.")
    def remove_channels(self) -> None:
        rows = sorted({index.row() for index in self.tableWidget_Edit_channels.selectedIndexes()}, reverse=True)
        for row in rows:
            if row >= 4:
                self.tableWidget_Edit_channels.removeRow(row)

    def averaging(self, channel_name: str) -> float:
        return average_channel(self._groups(), channel_name, self.doubleSpinBox_Start.value(), self.doubleSpinBox_End.value())

    def updating(self) -> None:
        if not self._check_ready(require_range=True):
            return

        self._refresh_average_table()
        self.statusbar.showMessage("Averaging values updated.")

    def _refresh_average_table(self) -> None:
        ref_temp = self._ambient_temperature()
        for row in range(4, self.tableWidget_Edit_channels.rowCount()):
            actual_channel = self._actual_channel_for_row(row)
            if not actual_channel:
                self._clear_general_average_row(row)
                continue
            try:
                value = self.averaging(actual_channel)
            except (KeyError, ValueError):
                self._clear_general_average_row(row)
                continue
            self._set_general_average_row(row, value, ref_temp)

        self._update_special_row(0, self.fuel_channel, ref_temp, relative=False)
        self._update_special_row(1, self.RAD_channels, ref_temp, relative=True)
        self._update_special_row(2, self.OC_channels, ref_temp, relative=True)
        self._update_special_row(3, self.CAC_channels, ref_temp, relative=True)
    def add_specials(self) -> None:
        if not self._check_ready(require_range=True):
            return

        selected = [item.text() for item in self.listView_Recording_channels.selectedItems()]
        if not selected:
            return

        index = self.comboBox_Specials.currentIndex()
        if index == 0:
            self.fuel_channel = selected[:1]
        elif index == 1:
            self.RAD_channels = selected
        elif index == 2:
            self.OC_channels = selected
        elif index == 3:
            self.CAC_channels = selected
        self.updating()

    def remove_specials(self) -> None:
        index = self.comboBox_Specials.currentIndex()
        if index == 0:
            self.fuel_channel = []
        elif index == 1:
            self.RAD_channels = []
        elif index == 2:
            self.OC_channels = []
        elif index == 3:
            self.CAC_channels = []
        self.tableWidget_Edit_channels.setItem(index, 1, QtWidgets.QTableWidgetItem(""))
        self.tableWidget_Edit_channels.setItem(index, 2, QtWidgets.QTableWidgetItem(""))

    def clearing(self) -> None:
        self.fuel_channel = []
        self.RAD_channels = []
        self.OC_channels = []
        self.CAC_channels = []
        self.tableWidget_Edit_channels.setRowCount(4)
        for row, text in enumerate(["fuel rate", "RAD \uc804\ub2e8", "OC \uc804\ub2e8", "CAC \uc804\ub2e8"]):
            self.tableWidget_Edit_channels.setItem(row, 0, QtWidgets.QTableWidgetItem(text))
            self.tableWidget_Edit_channels.setItem(row, 1, QtWidgets.QTableWidgetItem(""))
            self.tableWidget_Edit_channels.setItem(row, 2, QtWidgets.QTableWidgetItem(""))

    def _reset_import_state(self) -> None:
        self.df = pd.DataFrame()
        self.grouped_ones = pd.DataFrame()
        self.grouped_tens = pd.DataFrame()
        self.grouped_hundreds = pd.DataFrame()
        self.result_path = None
        self.average_baseline_s = None
        self.isPlotted = False
        self.listView_Sampling_channels.clear()
        self.listView_Recording_channels.clear()
        self.plotWidget.clear()
        self.clearing()

    def previewing(self) -> None:
        if not self._check_ready(require_range=True):
            return
        self.applying()
        self.updating()
        dialog = PreviewDialog(
            self.header_df,
            self._sub_dataframe(),
            self._main_dataframe(),
            self.doubleSpinBox_Start.value(),
            self.doubleSpinBox_End.value(),
            self.input_path,
            self,
        )
        dialog.exec()
        self.statusbar.showMessage("Preview closed.")

    def output(self) -> None:
        if not self._check_ready(require_range=True):
            return
        self.applying()
        self.updating()
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save As",
            str((self.input_path.parent if self.input_path else Path.cwd()) / "Preview_result.xlsx"),
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not file_path:
            return
        export_average_excel(
            file_path,
            self.header_df,
            self._sub_dataframe(),
            self._main_dataframe(),
            self.doubleSpinBox_Start.value(),
            self.doubleSpinBox_End.value(),
            self.input_path,
        )
        self.statusbar.showMessage(f"Excel exported: {file_path}")

    def _show_import_progress(self, input_path: Path) -> None:
        self._hide_import_progress()
        progress = QtWidgets.QProgressDialog(self)
        progress.setWindowTitle("Importing IAD")
        progress.setLabelText(f"Importing and converting...\n{input_path.name}")
        progress.setCancelButton(None)
        progress.setWindowFlag(QtCore.Qt.WindowType.WindowCloseButtonHint, False)
        progress.setRange(0, 0)
        progress.setMinimumDuration(0)
        progress.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self.import_progress = progress
        progress.show()
        QtWidgets.QApplication.processEvents()

    def _hide_import_progress(self) -> None:
        if self.import_progress is not None:
            self.import_progress.close()
            self.import_progress.deleteLater()
            self.import_progress = None

    def _set_busy(self, busy: bool) -> None:
        self.pushButton_Files.setEnabled(not busy)
        self.pushButton_Files_import.setEnabled(not busy)
        self.lineEdit_Files.setEnabled(not busy)

    def _plot_range_changed(self, start_s: float, end_s: float) -> None:
        self.doubleSpinBox_Start.blockSignals(True)
        self.doubleSpinBox_End.blockSignals(True)
        self.doubleSpinBox_Start.setValue(start_s)
        self.doubleSpinBox_End.setValue(end_s)
        self.doubleSpinBox_Start.blockSignals(False)
        self.doubleSpinBox_End.blockSignals(False)
        if not self.radioButton_User_defined.isChecked() and start_s == end_s:
            self.average_baseline_s = start_s
            self.statusbar.showMessage(f"Baseline: {start_s:.1f}s. Press << or >> to apply fixed averaging period.")
        else:
            self.statusbar.showMessage(f"Averaging range: {min(start_s, end_s):.1f}s ~ {max(start_s, end_s):.1f}s")

    def _spin_range_changed(self) -> None:
        self.plotWidget.set_range(self.doubleSpinBox_Start.value(), self.doubleSpinBox_End.value())

    def _radio_mode_changed(self) -> None:
        user_defined = self.radioButton_User_defined.isChecked()
        self.plotWidget.set_user_defined_range(user_defined)
        self.statusbar.showMessage(self._plot_help_text())

    def _plot_help_text(self) -> str:
        if self.radioButton_User_defined.isChecked():
            return "Wheel: zoom, left-drag: pan, double-click twice: averaging range."
        period = "5 minutes" if self.radioButton_Five_min.isChecked() else "10 minutes"
        return f"Wheel: zoom, left-drag: pan, double-click: baseline, << or >>: {period} averaging range."

    def _apply_period(self, forward: bool) -> None:
        baseline = self.average_baseline_s if self.average_baseline_s is not None else self.doubleSpinBox_Start.value()
        period = 300.0 if self.radioButton_Five_min.isChecked() else 600.0

        if self.radioButton_User_defined.isChecked():
            self.plotWidget.set_range(self.doubleSpinBox_Start.value(), self.doubleSpinBox_End.value())
            return

        if forward:
            start = baseline
            end = min(baseline + period, self._max_time())
        else:
            start = max(baseline - period, 0.0)
            end = baseline

        self.doubleSpinBox_Start.blockSignals(True)
        self.doubleSpinBox_End.blockSignals(True)
        self.doubleSpinBox_Start.setValue(start)
        self.doubleSpinBox_End.setValue(end)
        self.doubleSpinBox_Start.blockSignals(False)
        self.doubleSpinBox_End.blockSignals(False)
        self.plotWidget.set_range(start, end)
        self.statusbar.showMessage(f"Averaging range: {start:.1f}s ~ {end:.1f}s")

    def _series_for_channel(self, channel_name: str) -> dict | None:
        for df in self._groups().values():
            if df.empty or channel_name not in df.columns:
                continue
            time_column = df.columns[0]
            plot_df = pd.DataFrame(
                {
                    "x": pd.to_numeric(df[time_column], errors="coerce"),
                    "y": pd.to_numeric(df[channel_name], errors="coerce"),
                }
            )
            plot_df = plot_df[plot_df["x"].notna()].copy()
            if plot_df.empty or plot_df["y"].notna().sum() == 0:
                return None
            return {
                "name": channel_name,
                "x": plot_df["x"].to_numpy(),
                "y": plot_df["y"].to_numpy(),
            }
        return None

    def _channel_names(self) -> list[str]:
        seen = set()
        channels = []
        for df in self._groups().values():
            if df.empty:
                continue
            for column in df.columns[1:]:
                name = str(column)
                if not name or name.startswith("Unnamed") or name in seen:
                    continue
                if not self._channel_has_any_numeric_value(df, column):
                    continue
                seen.add(name)
                channels.append(name)
        return channels

    def _channel_has_any_numeric_value(self, df: pd.DataFrame, column: str) -> bool:
        return pd.to_numeric(df[column], errors="coerce").notna().any()

    def _groups(self) -> dict[int, pd.DataFrame]:
        return {
            1: self.grouped_ones,
            10: self.grouped_tens,
            100: self.grouped_hundreds,
        }

    def _max_time(self) -> float:
        max_time = 0.0
        for df in self._groups().values():
            if not df.empty:
                max_time = max(max_time, float(pd.to_numeric(df.iloc[:, 0], errors="coerce").max()))
        return max_time

    def _existing_table_channels(self) -> set[str]:
        existing = set()
        for row in range(self.tableWidget_Edit_channels.rowCount()):
            item = self.tableWidget_Edit_channels.item(row, 0)
            if item and item.text().strip():
                existing.add(item.text().strip())
        return existing

    def _existing_mapped_channels(self) -> set[str]:
        existing = set()
        for row in range(4, self.tableWidget_Edit_channels.rowCount()):
            actual_channel = self._actual_channel_for_row(row)
            if actual_channel:
                existing.add(actual_channel)
        return existing

    def _first_unmapped_general_row(self) -> int | None:
        for row in range(4, self.tableWidget_Edit_channels.rowCount()):
            item = self.tableWidget_Edit_channels.item(row, 0)
            if item and item.text().strip() and not item.data(QtCore.Qt.ItemDataRole.UserRole):
                return row
        return None

    def _actual_channel_for_row(self, row: int) -> str:
        item = self.tableWidget_Edit_channels.item(row, 0)
        if not item:
            return ""
        mapped = item.data(QtCore.Qt.ItemDataRole.UserRole)
        return str(mapped).strip() if mapped else item.text().strip()

    def _set_actual_channel(self, row: int, actual_channel: str) -> None:
        item = self.tableWidget_Edit_channels.item(row, 0)
        if item is None:
            item = QtWidgets.QTableWidgetItem(actual_channel)
            self.tableWidget_Edit_channels.setItem(row, 0, item)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, actual_channel)
        item.setToolTip(f"IAD channel: {actual_channel}")
    def _ambient_temperature(self) -> float:
        text = self.info_edits[7].text().strip()
        return float(text) if text else 0.0

    def _set_general_average_row(self, row: int, mean_value: float, ref_temp: float) -> None:
        self.tableWidget_Edit_channels.setItem(row, 1, QtWidgets.QTableWidgetItem(str(mean_value)))
        self.tableWidget_Edit_channels.setItem(row, 2, QtWidgets.QTableWidgetItem(str(round(mean_value - ref_temp, 1))))

    def _clear_general_average_row(self, row: int) -> None:
        self.tableWidget_Edit_channels.setItem(row, 1, QtWidgets.QTableWidgetItem(""))
        self.tableWidget_Edit_channels.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
    def _update_special_row(self, row: int, channels: list[str], ref_temp: float, relative: bool) -> None:
        if not channels:
            return
        values = []
        for channel in channels:
            try:
                values.append(self.averaging(channel))
            except (KeyError, ValueError):
                continue
        if not values:
            return
        mean_value = round(sum(values) / len(values), 1)
        self.tableWidget_Edit_channels.setItem(row, 1, QtWidgets.QTableWidgetItem(str(mean_value)))
        if relative:
            self.tableWidget_Edit_channels.setItem(row, 2, QtWidgets.QTableWidgetItem(str(round(mean_value - ref_temp, 1))))

    def _main_dataframe(self) -> pd.DataFrame:
        rows = []
        for row in range(4, self.tableWidget_Edit_channels.rowCount()):
            channel_item = self.tableWidget_Edit_channels.item(row, 0)
            value_item = self.tableWidget_Edit_channels.item(row, 1)
            relative_item = self.tableWidget_Edit_channels.item(row, 2)
            if not channel_item or not value_item:
                continue
            name = channel_item.text().strip()
            value_text = value_item.text().strip()
            relative_text = relative_item.text().strip() if relative_item else ""
            if not name or not value_text:
                continue
            try:
                relative_value = float(relative_text) if relative_text else None
                rows.append([name, float(value_text), relative_value])
            except ValueError:
                continue
        return pd.DataFrame(rows)

    def _sub_dataframe(self) -> pd.DataFrame:
        rows = []
        for row in range(4):
            channel_item = self.tableWidget_Edit_channels.item(row, 0)
            value_item = self.tableWidget_Edit_channels.item(row, 1)
            relative_item = self.tableWidget_Edit_channels.item(row, 2)
            rows.append([
                channel_item.text().strip() if channel_item else "",
                value_item.text().strip() if value_item else "",
                relative_item.text().strip() if relative_item else "",
            ])
        return pd.DataFrame(rows)

    def _check_ready(self, require_range: bool) -> bool:
        if self.df.empty:
            QtWidgets.QMessageBox.warning(self, "No raw data", "Test data is required. Please import the test data.")
            return False
        if require_range and self.doubleSpinBox_Start.value() == self.doubleSpinBox_End.value():
            QtWidgets.QMessageBox.warning(self, "No averaging period", "Please define the time period to be averaged.")
            return False
        return True


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
