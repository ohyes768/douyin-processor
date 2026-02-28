"""
音频提取器
使用FFmpeg从视频中提取音频
"""

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from ffmpy import FFmpeg

from src.utils import ensure_dir, delete_file, get_file_size, format_size


class AudioExtractor:
    """音频提取器"""

    def __init__(
        self,
        cache_dir: str = "data/temp",
        sample_rate: int = 16000,
        channels: int = 1
    ):
        """初始化音频提取器

        Args:
            cache_dir: 缓存目录
            sample_rate: 采样率（默认16000Hz，阿里云ASR要求）
            channels: 声道数（默认1为单声道）
        """
        self.cache_dir = Path(cache_dir)
        self.sample_rate = sample_rate
        self.channels = channels

        # 确保缓存目录存在
        ensure_dir(self.cache_dir)

        logger.info(
            f"音频提取器初始化完成: "
            f"采样率={sample_rate}Hz, 声道={channels}"
        )

    async def extract_from_file(
        self,
        video_file: str,
        output_format: str = "wav"
    ) -> Optional[str]:
        """从视频文件提取音频

        Args:
            video_file: 视频文件路径
            output_format: 输出格式（wav/mp3）

        Returns:
            音频文件路径，失败返回None
        """
        video_path = Path(video_file)

        if not video_path.exists():
            logger.error(f"视频文件不存在: {video_file}")
            return None

        # 生成输出文件名
        output_file = self.cache_dir / f"{video_path.stem}.{output_format}"

        logger.info(f"开始提取音频: {video_file} -> {output_file}")

        try:
            # 构建FFmpeg命令
            # -vn: 不处理视频流
            # -acodec pcm_s16le: 音频编码格式
            # -ar: 采样率
            # -ac: 声道数
            ff = FFmpeg(
                inputs={str(video_path): None},
                outputs={
                    str(output_file): (
                        f"-vn -acodec pcm_s16le "
                        f"-ar {self.sample_rate} "
                        f"-ac {self.channels}"
                    )
                }
            )

            # 执行转换
            await asyncio.to_thread(ff.run)

            # 验证输出文件
            if output_file.exists():
                file_size = get_file_size(str(output_file))
                logger.info(
                    f"音频提取成功: {output_file} "
                    f"({format_size(file_size)})"
                )
                return str(output_file)
            else:
                logger.error(f"音频文件未生成: {output_file}")
                return None

        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            # 清理可能生成的部分文件
            delete_file(str(output_file))
            return None

    def cleanup(self, older_than: int = 3600) -> int:
        """清理临时音频文件

        Args:
            older_than: 清理多少秒之前的文件（默认1小时）

        Returns:
            清理的文件数量
        """
        import time

        current_time = time.time()
        cleaned_count = 0

        try:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    # 检查文件修改时间
                    file_mtime = file_path.stat().st_mtime
                    if current_time - file_mtime > older_than:
                        if delete_file(str(file_path)):
                            cleaned_count += 1
                            logger.debug(f"清理临时文件: {file_path}")

            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个临时音频文件")

            return cleaned_count

        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return 0
