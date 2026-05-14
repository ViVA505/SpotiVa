from __future__ import annotations

from collections.abc import Callable, Mapping


class YtDlpProgressHook:
    def __init__(self, callback: Callable[[int, int], None] | None) -> None:
        self._callback = callback

    def __call__(self, payload: Mapping[str, object]) -> None:
        if not self._callback:
            return

        status = str(payload.get("status", "")).strip().lower()
        if status not in {"downloading", "finished"}:
            return

        downloaded = self._safe_int(payload.get("downloaded_bytes"))
        total = self._safe_int(
            payload.get("total_bytes") or payload.get("total_bytes_estimate")
        )

        if status == "finished":
            resolved_total = total or downloaded
            self._callback(resolved_total, resolved_total)
            return

        self._callback(downloaded, total)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0
