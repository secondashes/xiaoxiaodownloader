"""PyQt5 + PyQtWebEngine 集成示例（大框架对接演示）。

展示如何把 BunkrPlugin 接入一个带浏览器的 Qt 主程序：
  - 启动后端插件（子进程 stdio）
  - 浏览器内检测 bunkr 链接（悬停提示 + 请求拦截）
  - 检测到时弹窗询问，调用后端解析

依赖：pip install PyQt5 PyQtWebEngine

运行：python pyqt_integration.py

说明：这里演示「检测到链接 -> 提示 -> inspect 解析」；完整下载流程是
  inspect -> 监听 inspect_complete 拿到文件列表 -> 让用户勾选 -> 调 download()
"""

import sys

from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMainWindow,
    QMessageBox,
    QToolBar,
)
from PyQt5.QtWebEngineWidgets import (
    QWebEngineProfile,
    QWebEngineUrlRequestInterceptor,
    QWebEngineView,
)

from bunkr_plugin import BunkrPlugin, extract_bunkr_url, is_bunkr_url


class QtBunkrPlugin(QObject):
    """把后端事件桥接到 Qt 信号（线程安全，自动切回主线程）。"""

    event = pyqtSignal(dict)          # 任意后端事件
    ready = pyqtSignal()              # 后端就绪
    bunkr_detected = pyqtSignal(str)  # 检测到 bunkr 链接

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.plugin = BunkrPlugin()
        self.plugin.on_any(self.event.emit)
        self.plugin.on("ready", lambda _ev: self.ready.emit())

    # 透传常用命令
    def wait_ready(self, timeout: float = 15.0) -> bool:
        return self.plugin.wait_ready(timeout)

    def inspect(self, url: str, options: dict | None = None) -> None:
        self.plugin.inspect(url, options)

    def download(self, url, items, options=None, album_name="", album_id=None) -> None:
        self.plugin.download(url, items, options, album_name, album_id)

    def send(self, cmd: dict) -> None:
        self.plugin.send(cmd)

    def stop(self) -> None:
        self.plugin.stop()


class BunkrRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """拦截浏览器发起的请求，命中 bunkr 链接时通知主程序。"""

    def __init__(self, bridge: QtBunkrPlugin):
        super().__init__()
        self._bridge = bridge

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if is_bunkr_url(url):
            # 该回调在 IO 线程执行，pyqtSignal 会自动队列到主线程
            self._bridge.bunkr_detected.emit(url)


class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bunkr 插件示例浏览器")
        self.resize(1200, 800)

        self.bridge = QtBunkrPlugin()
        self.bridge.bunkr_detected.connect(self._prompt_bunkr)
        self.bridge.event.connect(self._on_event)

        # 请求拦截器需在创建 QWebEngineView 之前设置
        self._interceptor = BunkrRequestInterceptor(self.bridge)
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self._interceptor)

        self.view = QWebEngineView()
        self.view.setUrl(QUrl("https://www.google.com"))
        self.view.page().linkHovered.connect(self._on_hover)
        self.setCentralWidget(self.view)

        # 工具栏：手动从剪贴板解析 bunkr 链接
        toolbar = QToolBar()
        act_clipboard = QAction("解析剪贴板链接", self)
        act_clipboard.triggered.connect(self._check_clipboard)
        toolbar.addAction(act_clipboard)
        self.addToolBar(toolbar)

        self.statusBar().showMessage("后端启动中...")
        # 就绪后更新状态栏
        self.bridge.ready.connect(lambda: self.statusBar().showMessage("Bunkr 后端已就绪"))

    def _on_event(self, ev: dict) -> None:
        if ev.get("event") == "log":
            msg = f"[{ev.get('type', '')}] {ev.get('message', '')}"
            self.statusBar().showMessage(msg, 8000)

    def _on_hover(self, url: str) -> None:
        if is_bunkr_url(url):
            self.statusBar().showMessage("检测到 Bunkr 链接：" + url)

    def _prompt_bunkr(self, url: str) -> None:
        ret = QMessageBox.question(
            self,
            "检测到 Bunkr 链接",
            "是否用下载器解析该链接？\n\n" + url,
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.bridge.inspect(url)
            QMessageBox.information(self, "已提交", "已提交解析请求，请监听 inspect_complete 事件获取文件列表。")

    def _check_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        url = extract_bunkr_url(text)
        if url:
            self._prompt_bunkr(url)
        else:
            QMessageBox.information(self, "提示", "剪贴板中没有 Bunkr 链接")

    def closeEvent(self, event) -> None:
        self.bridge.stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    win = BrowserWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
