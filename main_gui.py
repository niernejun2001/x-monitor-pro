#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X Monitor Pro - PyQt6 Desktop Application
将Flask Web应用包装为PyQt6桌面应用
"""

import sys
import os
import signal
import time
import threading
import requests
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QProgressBar, QStackedLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QFont, QDesktopServices

# 导入Flask应用和监控状态
from app import app as flask_app, save_state, save_processed_users, monitor_active, load_state


class SignalEmitter(QObject):
    """信号发射器"""
    ready = pyqtSignal()
    error = pyqtSignal(str)


class FlaskServer(threading.Thread):
    """在后台线程运行Flask服务器"""

    def __init__(self, signal_emitter):
        super().__init__(daemon=True)
        self.signal_emitter = signal_emitter
        self.server = None

    def run(self):
        """启动Flask服务器"""
        try:
            # 禁用Flask的重新加载和日志
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)

            # 使用 werkzeug 的 make_server 以便可以关闭
            from werkzeug.serving import make_server
            self.server = make_server('127.0.0.1', 5000, flask_app, threaded=True)
            self.server.serve_forever()
        except Exception as e:
            self.signal_emitter.error.emit(f"Flask启动失败: {str(e)}")

    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.shutdown()


class ExternalLinkPage(QWebEnginePage):
    """将外部链接交给系统浏览器打开。"""

    def __init__(self, profile=None, parent=None):
        if profile is None:
            super().__init__(parent)
        else:
            super().__init__(profile, parent)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if self._open_external_url(url):
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _window_type):
        # 处理 target="_blank" / window.open
        popup_page = ExternalLinkPage(self.profile(), self)
        popup_page.urlChanged.connect(popup_page._open_external_url)
        return popup_page

    def _open_external_url(self, url):
        """只将外部 http(s) 链接交给系统浏览器，忽略 about:blank 等临时页面。"""
        scheme = (url.scheme() or "").lower()
        if scheme not in {"http", "https"}:
            return False

        host = (url.host() or "").lower()
        if host and host not in {"127.0.0.1", "localhost"}:
            QDesktopServices.openUrl(url)
            return True
        return False


class XMonitorGUI(QMainWindow):
    """X Monitor Pro 主窗口"""

    def __init__(self):
        super().__init__()
        self.flask_thread = None
        self.signal_emitter = SignalEmitter()
        self.signal_emitter.ready.connect(self.on_server_ready)
        self.signal_emitter.error.connect(self.on_server_error)

        # Qt 模式下 app.py 不会执行 __main__，需要显式加载持久化状态
        try:
            load_state()
        except Exception as e:
            print(f"加载持久化状态失败: {e}")

        # 初始化UI
        self.init_ui()

        # 启动Flask服务器
        self.start_flask_server()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("X Monitor Pro - 推文评论监控")
        self.setGeometry(100, 100, 1400, 900)

        # 设置窗口图标（可选）
        try:
            icon = QIcon()
            self.setWindowIcon(icon)
        except Exception:
            pass

        # 创建中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 使用堆叠布局：加载页和网页页完全切换，避免残留占位导致白块
        self.stacked_layout = QStackedLayout(central_widget)
        self.stacked_layout.setContentsMargins(0, 0, 0, 0)
        self.stacked_layout.setSpacing(0)

        # 加载页
        loading_page = QWidget()
        loading_layout = QVBoxLayout(loading_page)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(8)

        self.loading_label = QLabel("正在启动服务器...")
        font = QFont()
        font.setPointSize(12)
        self.loading_label.setFont(font)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 无限进度条

        loading_layout.addStretch()
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.progress_bar)
        loading_layout.addStretch()

        # 网页页
        self.web_view = QWebEngineView()
        self.web_page = ExternalLinkPage(parent=self.web_view)
        self.web_view.setPage(self.web_page)

        self.stacked_layout.addWidget(loading_page)
        self.stacked_layout.addWidget(self.web_view)
        self.stacked_layout.setCurrentIndex(0)

    def start_flask_server(self):
        """在后台线程启动Flask服务器"""
        self.flask_thread = FlaskServer(self.signal_emitter)
        self.flask_thread.start()

        # 开始检查服务器是否就绪
        self.check_server()

    def check_server(self):
        """检查服务器是否就绪"""
        try:
            response = requests.get('http://127.0.0.1:5000/', timeout=1)
            if response.status_code == 200:
                self.signal_emitter.ready.emit()
                return
        except Exception:
            pass

        # 如果服务器还未就绪，1秒后重试
        QTimer.singleShot(1000, self.check_server)

    def on_server_ready(self):
        """服务器就绪时的回调"""
        # 切换到网页页
        self.stacked_layout.setCurrentIndex(1)

        # 加载应用页面
        self.web_view.load(QUrl("http://127.0.0.1:5000"))

    def on_server_error(self, error_msg):
        """服务器错误时的回调"""
        self.loading_label.setText(f"错误: {error_msg}")
        self.progress_bar.setVisible(False)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 保存数据
        try:
            save_state()
            save_processed_users()
        except Exception as e:
            print(f"保存数据失败: {e}")

        # 停止Flask服务器
        if self.flask_thread:
            self.flask_thread.stop()

        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 创建主窗口
    window = XMonitorGUI()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
