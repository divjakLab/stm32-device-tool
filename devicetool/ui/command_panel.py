"""Command library panel: grouped saved commands, editing, import/export."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.commands import Command, CommandLibrary, placeholders
from ..core.storage import Settings

_ROLE = Qt.ItemDataRole.UserRole


class CommandDialog(QDialog):
    def __init__(self, parent, groups: list[str], cmd: Command | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command")
        self.name = QLineEdit(cmd.name if cmd else "")
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(groups or ["General"])
        self.group.setCurrentText(cmd.group if cmd else (groups[0] if groups else "General"))
        self.text = QLineEdit(cmd.text if cmd else "")
        self.text.setMinimumWidth(360)
        self.text.setPlaceholderText("e.g. wifi set {ssid} {password}")
        hint = QLabel("<small>Write <b>{name}</b> for a value you fill in when sending.</small>")
        form = QFormLayout(self)
        form.addRow("Name", self.name)
        form.addRow("Group", self.group)
        form.addRow("Command", self.text)
        form.addRow("", hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        if not self.text.text().strip():
            QMessageBox.warning(self, "Command", "The command text can't be empty.")
            return
        self.accept()

    def command(self) -> Command:
        text = self.text.text().strip()
        return Command(self.name.text().strip() or text, text,
                       self.group.currentText().strip() or "General")


class PlaceholderDialog(QDialog):
    def __init__(self, parent, cmd: Command, remembered: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle(cmd.name)
        form = QFormLayout(self)
        form.addRow(QLabel(f"<code>{cmd.text}</code>"))
        self._fields: dict[str, QLineEdit] = {}
        for name in placeholders(cmd.text):
            edit = QLineEdit(str(remembered.get(name, "")))
            self._fields[name] = edit
            form.addRow(name, edit)
        buttons = QDialogButtonBox()
        buttons.addButton("Send", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {k: e.text() for k, e in self._fields.items()}


class _Tree(QTreeWidget):
    dropped = Signal()

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.dropped.emit()


class CommandPanel(QWidget):
    commandPicked = Signal(object, bool)   # Command, send_now

    def __init__(self, library_path: Path, settings: Settings) -> None:
        super().__init__()
        self._path = library_path
        self._settings = settings
        self.library = CommandLibrary.load(library_path)

        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.invisibleRootItem().setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemActivated.connect(self._activated)
        self.tree.dropped.connect(self._sync_from_tree)

        def btn(text, slot, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        row1 = QHBoxLayout()
        row1.addWidget(btn("➕ New", self._new, "Create a command"))
        row1.addWidget(btn("Edit", self._edit, "Edit the selected command"))
        row1.addWidget(btn("Duplicate", self._duplicate, "Copy the selected command"))
        row1.addWidget(btn("Delete", self._delete, "Delete the selected command"))
        row2 = QHBoxLayout()
        row2.addWidget(btn("Import…", self._import, "Add commands from a .json file"))
        row2.addWidget(btn("Export…", self._export, "Save all commands to a .json file"))
        row2.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("<b>Commands</b> <small>(click: edit · double-click: send)</small>"))
        lay.addWidget(self.tree, 1)
        lay.addLayout(row1)
        lay.addLayout(row2)
        self._rebuild()

    # -- model <-> tree --------------------------------------------------------

    def _rebuild(self) -> None:
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for index, cmd in enumerate(self.library.commands):
            parent = groups.get(cmd.group)
            if parent is None:
                parent = QTreeWidgetItem([cmd.group])
                parent.setFont(0, bold)
                parent.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                self.tree.addTopLevelItem(parent)
                groups[cmd.group] = parent
            item = QTreeWidgetItem([cmd.name])
            item.setToolTip(0, cmd.text)
            item.setData(0, _ROLE, index)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                          Qt.ItemFlag.ItemIsDragEnabled)
            parent.addChild(item)
        self.tree.expandAll()

    def _save(self) -> None:
        try:
            self.library.save(self._path)
        except OSError as exc:
            QMessageBox.warning(self, "Commands", f"Could not save the commands:\n{exc}")

    def _sync_from_tree(self) -> None:
        old = self.library.commands
        new: list[Command] = []
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                index = group_item.child(j).data(0, _ROLE)
                new.append(replace(old[index], group=group_item.text(0)))
        self.library.commands = new
        self._save()
        self._rebuild()

    def _selected_index(self) -> int | None:
        item = self.tree.currentItem()
        if item is None or item.data(0, _ROLE) is None:
            QMessageBox.information(self, "Commands", "Select a command first.")
            return None
        return item.data(0, _ROLE)

    # -- actions ---------------------------------------------------------------

    def _clicked(self, item: QTreeWidgetItem) -> None:
        index = item.data(0, _ROLE)
        if index is not None:
            self.commandPicked.emit(self.library.commands[index], False)

    def _activated(self, item: QTreeWidgetItem) -> None:
        index = item.data(0, _ROLE)
        if index is not None:
            self.commandPicked.emit(self.library.commands[index], True)

    def _new(self) -> None:
        dlg = CommandDialog(self, self.library.groups())
        if dlg.exec():
            self.library.commands.append(dlg.command())
            self._save()
            self._rebuild()

    def _edit(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        dlg = CommandDialog(self, self.library.groups(), self.library.commands[index])
        if dlg.exec():
            self.library.commands[index] = dlg.command()
            self._save()
            self._rebuild()

    def _duplicate(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        c = self.library.commands[index]
        self.library.commands.insert(index + 1, replace(c, name=f"{c.name} copy"))
        self._save()
        self._rebuild()

    def _delete(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        c = self.library.commands[index]
        if QMessageBox.question(self, "Delete command", f"Delete “{c.name}”?") == \
                QMessageBox.StandardButton.Yes:
            del self.library.commands[index]
            self._save()
            self._rebuild()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import commands", str(Path.home()),
                                              "Command library (*.json)")
        if not path:
            return
        try:
            n = self.library.import_file(Path(path))
        except ValueError as exc:
            QMessageBox.warning(self, "Import commands", str(exc))
            return
        self._save()
        self._rebuild()
        QMessageBox.information(self, "Import commands", f"Imported {n} new command(s).")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export commands",
                                              str(Path.home() / "commands.json"),
                                              "Command library (*.json)")
        if path:
            try:
                self.library.export_file(Path(path))
            except OSError as exc:
                QMessageBox.warning(self, "Export commands", str(exc))
