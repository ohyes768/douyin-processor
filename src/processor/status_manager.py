"""
状态管理器
管理视频处理状态，使用 JSON 文件存储
"""

import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime
from loguru import logger

from src.models import ProcessStatus
from src.utils import load_json, save_json


class StatusManager:
    """状态管理器"""

    def __init__(self, status_file: str = "data/status.json"):
        """初始化状态管理器

        Args:
            status_file: 状态文件路径
        """
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载现有状态
        self._lock = asyncio.Lock()
        self._data = self._load()

        logger.info(f"状态管理器初始化完成: {status_file}")

    def _load(self) -> dict:
        """加载状态文件"""
        if self.status_file.exists():
            return load_json(str(self.status_file))
        return {
            "last_updated": datetime.now().isoformat(),
            "videos": {}
        }

    def _save(self):
        """保存状态文件"""
        self._data["last_updated"] = datetime.now().isoformat()
        save_json(self._data, str(self.status_file))

    async def get_status(self, aweme_id: str) -> Optional[str]:
        """获取视频处理状态

        Args:
            aweme_id: 视频 ID

        Returns:
            状态（pending/processing/completed/failed），不存在返回 None
        """
        async with self._lock:
            video_data = self._data.get("videos", {}).get(aweme_id)
            return video_data.get("status") if video_data else None

    async def set_status(
        self,
        aweme_id: str,
        status: str,
        error: str = ""
    ):
        """设置视频处理状态

        Args:
            aweme_id: 视频 ID
            status: 状态
            error: 错误信息
        """
        async with self._lock:
            now = datetime.now().isoformat()

            if aweme_id not in self._data.get("videos", {}):
                self._data.setdefault("videos", {})[aweme_id] = {
                    "created_at": now
                }

            self._data["videos"][aweme_id].update({
                "status": status,
                "updated_at": now
            })

            if error:
                self._data["videos"][aweme_id]["error"] = error

            self._save()

    async def mark_processing(self, aweme_id: str):
        """标记为处理中"""
        await self.set_status(aweme_id, "processing")

    async def mark_completed(self, aweme_id: str):
        """标记为已完成"""
        await self.set_status(aweme_id, "completed")

    async def mark_failed(self, aweme_id: str, error: str):
        """标记为失败"""
        await self.set_status(aweme_id, "failed", error)

    async def is_completed(self, aweme_id: str) -> bool:
        """检查视频是否已完成处理"""
        status = await self.get_status(aweme_id)
        return status == "completed"

    async def is_processing(self, aweme_id: str) -> bool:
        """检查视频是否正在处理"""
        status = await self.get_status(aweme_id)
        return status == "processing"

    async def is_failed(self, aweme_id: str) -> bool:
        """检查视频是否处理失败"""
        status = await self.get_status(aweme_id)
        return status == "failed"

    async def get_pending_count(self) -> int:
        """获取待处理视频数量"""
        async with self._lock:
            videos = self._data.get("videos", {})
            return sum(1 for v in videos.values() if v.get("status") == "pending")

    async def get_all_statuses(self) -> dict:
        """获取所有视频状态"""
        async with self._lock:
            return self._data.get("videos", {}).copy()

    async def mark_read(self, aweme_id: str, is_read: bool = True):
        """标记视频已读/未读

        Args:
            aweme_id: 视频 ID
            is_read: 是否已读
        """
        async with self._lock:
            now = datetime.now().isoformat()

            if aweme_id not in self._data.get("videos", {}):
                self._data.setdefault("videos", {})[aweme_id] = {
                    "created_at": now
                }

            if is_read:
                self._data["videos"][aweme_id]["is_read"] = True
                self._data["videos"][aweme_id]["read_at"] = now
            else:
                self._data["videos"][aweme_id]["is_read"] = False
                self._data["videos"][aweme_id]["read_at"] = None

            self._save()
            logger.info(f"视频 {aweme_id} 已标记为 {'已读' if is_read else '未读'}")

    async def hard_delete(self, aweme_id: str):
        """硬删除视频（从状态文件移除）

        Args:
            aweme_id: 视频 ID
        """
        async with self._lock:
            videos = self._data.get("videos", {})
            if aweme_id in videos:
                del videos[aweme_id]
                self._save()
                logger.info(f"视频 {aweme_id} 已从状态文件中删除")

    async def get_read_status(self, aweme_id: str) -> dict:
        """获取视频已读/收藏状态

        Args:
            aweme_id: 视频 ID

        Returns:
            包含 is_read 和 read_at 的字典
        """
        async with self._lock:
            video_data = self._data.get("videos", {}).get(aweme_id, {})
            return {
                "is_read": video_data.get("is_read", False),
                "read_at": video_data.get("read_at")
            }
