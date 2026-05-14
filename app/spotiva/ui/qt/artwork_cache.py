from __future__ import annotations

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


_USER_AGENT = "Mozilla/5.0"


class ArtworkCache(QObject):
    loaded = pyqtSignal(str, bytes)
    failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._network = QNetworkAccessManager(self)
        self._payloads: dict[str, bytes] = {}
        self._replies: dict[QNetworkReply, str] = {}
        self._pending_urls: set[str] = set()

    def payload(self, url: str) -> bytes:
        return self._payloads.get(url.strip(), b"")

    def store(self, url: str, payload: bytes) -> None:
        normalized_url = url.strip()
        if not normalized_url or not payload:
            return
        self._payloads[normalized_url] = payload
        self.loaded.emit(normalized_url, payload)

    def request(self, url: str) -> None:
        normalized_url = url.strip()
        if not normalized_url:
            return
        if normalized_url in self._payloads:
            self.loaded.emit(normalized_url, self._payloads[normalized_url])
            return
        if normalized_url in self._pending_urls:
            return

        request = QNetworkRequest(QUrl(normalized_url))
        request.setRawHeader(b"User-Agent", _USER_AGENT.encode("utf-8"))
        reply = self._network.get(request)
        self._pending_urls.add(normalized_url)
        self._replies[reply] = normalized_url
        reply.finished.connect(lambda current_reply=reply: self._finish(current_reply))

    def _finish(self, reply: QNetworkReply) -> None:
        url = self._replies.pop(reply, "")
        if url:
            self._pending_urls.discard(url)

        if url and reply.error() == QNetworkReply.NetworkError.NoError:
            payload = bytes(reply.readAll())
            if payload:
                self._payloads[url] = payload
                self.loaded.emit(url, payload)
            else:
                self.failed.emit(url)
        elif url:
            self.failed.emit(url)

        reply.deleteLater()
