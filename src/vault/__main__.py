import inspect
import logging
import os
import sys

from flask import Flask, request
from flask_cors import CORS
from hwilib import commands
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtUiTools import QUiLoader
from werkzeug.serving import make_server

loader = QUiLoader()


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


if hasattr(sys, "_MEIPASS"):  # dummy streams in noconsole mode
    f = open(os.devnull, "w")
    sys.stdin = f
    sys.stdout = f


class PermissionManager(QtCore.QObject):
    set_permission = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.allowed_origins = {}
        self.wait_condition = QtCore.QWaitCondition()
        self.mutex = QtCore.QMutex()

    def check_origin(self, origin):
        if origin not in self.allowed_origins:
            self.ask_permission(origin)
        return origin in self.allowed_origins

    def ask_permission(self, origin):
        self.mutex.lock()
        self.set_permission.emit(origin)
        self.wait_condition.wait(self.mutex)
        self.mutex.unlock()
        if window.response:
            self.allowed_origins[origin] = True


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ask_permission = False
        self.current_origin = None
        self.response = None
        self.main_dialog = UiMainDialog
        self.permission_dialog = UiPermissionDialog
        self.permission_dialog.accept_button.clicked.connect(self.accept_permission)
        self.permission_dialog.reject_button.clicked.connect(self.reject_permission)
        permission_manager.set_permission.connect(self.init_ask_permission)

    def init_ask_permission(self, origin):
        self.ask_permission = True
        self.current_origin = origin
        self.response = None
        label_text = self.permission_dialog.warning_label.text()
        self.permission_dialog.warning_label.setText(label_text.format(website=origin))
        self.permission_dialog.show()
        self.main_dialog.hide()

    def _base_permission_set(self, result):
        self.permission_dialog.hide()
        self.permission_dialog.warning_label.setText(
            self.permission_dialog.original_label
        )
        self.main_dialog.show()
        self.response = result
        self.ask_permission = False
        permission_manager.wait_condition.wakeAll()

    def accept_permission(self):
        self._base_permission_set(True)

    def reject_permission(self):
        self._base_permission_set(False)


app = QtWidgets.QApplication(sys.argv)


UiMainDialog = loader.load(resource_path("resources/main_window.ui"), None)
UiMainDialog.setWindowIcon(
    QtGui.QIcon(QtGui.QPixmap(resource_path("resources/logo.png")))
)
UiMainDialog.label.setPixmap(QtGui.QPixmap(resource_path("resources/logo.png")))
UiMainDialog.method_label.hide()
UiMainDialog.show()


UiPermissionDialog = loader.load(resource_path("resources/permission_dialog.ui"), None)
UiPermissionDialog.setWindowIcon(
    QtGui.QIcon(QtGui.QPixmap(resource_path("resources/logo.png")))
)
UiPermissionDialog.original_label = UiPermissionDialog.warning_label.text()


class ServerThread(QtCore.QThread):
    def __init__(self, app):
        super().__init__()
        self.server = make_server("127.0.0.1", 5000, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()


logging.basicConfig(level=logging.ERROR)

flask_app = Flask(__name__)
CORS(flask_app)

permission_manager = PermissionManager()


@flask_app.post("/hwi-bridge")
def hwi_bridge():
    origin = request.headers["Origin"]
    if not permission_manager.check_origin(origin):
        return {"success": False, "error": "User denied access"}, 401
    data = request.json
    if not data or "method" not in data or "args" not in data:
        return {"success": False, "error": "Invalid request"}, 400
    if not hasattr(commands, data["method"]):
        return {"success": False, "error": "Method not found"}, 404
    text = window.main_dialog.method_label.text()
    window.main_dialog.method_label.setText(text.format(method=data["method"]))
    window.main_dialog.method_label.show()
    try:
        method = getattr(commands, data["method"])
        # check if signature has client arg
        if "client" in inspect.signature(method).parameters:
            fingerprint = data["args"].pop(0)
            client = commands.find_device(fingerprint=fingerprint)
            if client is None:
                return {"success": False, "error": "Device not found or is locked"}, 404
            data["args"].insert(0, client)
        result = method(*data["args"])
    except Exception as e:
        return {"success": False, "error": str(e)}, 200
    finally:
        window.main_dialog.method_label.setText(text)
        window.main_dialog.method_label.hide()
    return {"success": True, "result": result}


thread = ServerThread(flask_app)
thread.start()

app.aboutToQuit.connect(thread.terminate)
window = MainWindow()
app.exec_()
