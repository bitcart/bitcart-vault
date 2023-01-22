import inspect
import logging
import os
import sys
import threading
import time

from flask import Flask, request
from flask_cors import CORS
from hwilib import commands
from PyQt5 import QtWidgets, uic
from werkzeug.serving import make_server


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class PermissionManager:
    def __init__(self):
        self.allowed_origins = {}

    def check_origin(self, origin):
        if origin not in self.allowed_origins:
            self.ask_permission(origin)
        return origin in self.allowed_origins

    def ask_permission(self, origin):
        window.ask_permission = True
        window.current_origin = origin
        window.response = None
        label_text = window.permission_dialog.warning_label.text()
        window.permission_dialog.warning_label.setText(
            label_text.format(website=origin)
        )
        window.permission_dialog.show()
        window.main_dialog.hide()
        while window.ask_permission:
            time.sleep(0.1)
        window.permission_dialog.warning_label.setText(label_text)
        if window.response:
            self.allowed_origins[origin] = True


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ask_permission = False
        self.current_origin = None
        self.response = None
        self.main_dialog = MainDialog()
        self.permission_dialog = PermissionDialog()
        self.permission_dialog.accept_button.clicked.connect(self.accept_permission)
        self.permission_dialog.reject_button.clicked.connect(self.reject_permission)

    def accept_permission(self):
        self.permission_dialog.close()
        self.main_dialog.show()
        self.response = True
        self.ask_permission = False

    def reject_permission(self):
        self.permission_dialog.close()
        self.main_dialog.show()
        self.response = False
        self.ask_permission = False


class MainDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("resources/main_window.ui"), self)
        self.method_label.hide()
        self.show()


class PermissionDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("resources/permission_dialog.ui"), self)


class ServerThread(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server("127.0.0.1", 5000, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


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

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
try:
    app.exec_()
finally:
    thread.shutdown()
