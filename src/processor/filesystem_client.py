"""
file-system-go 客户端
负责从 file-system-go 获取视频列表和下载视频
"""

import asyncio
from pathlib import Path
from typing import Optional, List
from loguru import logger
import httpx

from src.models import VideoFile


class FileSystemClient:
    """file-system-go 客户端"""

    def __init__(
        self,
        base_url: str,
        query_endpoint: str = "/api/videos/query",
        download_endpoint_template: str = "/api/videos/{id}/download",
        timeout: int = 300
    ):
        """初始化客户端

        Args:
            base_url: file-system-go 基础 URL
            query_endpoint: 查询接口路径
            download_endpoint_template: 下载接口路径模板
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.query_url = f"{base_url}{query_endpoint}"
        self.download_endpoint_template = download_endpoint_template
        self.timeout = timeout

        logger.info(f"file-system-go 客户端初始化完成: {base_url}")

    async def get_video_list(
        self,
        filters: dict = None
    ) -> List[VideoFile]:
        """获取视频列表

        Args:
            filters: 过滤条件，如 {"prefix": "audio", "suffix": ".mp4"}

        Returns:
            视频文件列表
        """
        logger.info("获取视频列表")

        # 构建请求体，符合 file-system-go 的格式
        request_body = {}
        if filters:
            request_body["filters"] = filters

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.query_url,
                    json=request_body
                )

                if response.status_code == 200:
                    data = response.json()

                    # 检查 success 字段
                    if not data.get("success", False):
                        logger.error(f"获取视频列表失败: {data.get('error', 'Unknown error')}")
                        return []

                    videos = []

                    for item in data.get("videos", []):
                        # 从文件名提取 aweme_id（格式为 xxx.wav）
                        filename = item.get("filename", "")
                        aweme_id = filename.replace(".wav", "")

                        # 获取 URL，如果是相对路径则拼接 base_url
                        url = item.get("url", "")
                        if url and not url.startswith("http"):
                            url = f"{self.base_url}{url}"

                        videos.append(VideoFile(
                            aweme_id=aweme_id,
                            filename=filename,
                            size=item.get("size", 0),
                            url=url
                        ))

                    logger.info(f"获取到 {len(videos)} 个视频")
                    return videos
                else:
                    logger.error(
                        f"获取视频列表失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return []

        except Exception as e:
            logger.error(f"获取视频列表异常: {e}")
            return []

    async def download_video(
        self,
        aweme_id: str,
        output_dir: str
    ) -> Optional[str]:
        """下载视频文件

        Args:
            aweme_id: 视频 ID
            output_dir: 输出目录

        Returns:
            下载的文件路径，失败返回 None
        """
        # 构建下载 URL
        download_url = f"{self.base_url}/api/videos/{aweme_id}/download"
        output_path = Path(output_dir) / f"{aweme_id}.mp4"

        logger.info(f"下载视频: {aweme_id} -> {output_path}")

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(download_url)

                if response.status_code == 200:
                    # 保存文件
                    with open(output_path, "wb") as f:
                        f.write(response.content)

                    file_size = output_path.stat().st_size
                    logger.info(
                        f"视频下载成功: {output_path} "
                        f"({file_size / 1024 / 1024:.2f} MB)"
                    )
                    return str(output_path)
                else:
                    logger.error(
                        f"视频下载失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"视频下载异常: {e}")
            return None
