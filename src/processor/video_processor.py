"""
视频处理器
协调整个视频处理流程：下载、提取音频、ASR识别、保存结果
"""

import asyncio
import time
from pathlib import Path
from typing import Optional
from loguru import logger

from src.models import TranscriptResult, ProcessResult
from src.processor.filesystem_client import FileSystemClient
from src.processor.audio_extractor import AudioExtractor
from src.processor.asr_client import AliyunASRClient
from src.processor.status_manager import StatusManager
from src.utils import delete_file, save_json


class VideoProcessor:
    """视频处理器"""

    def __init__(
        self,
        filesystem_client: FileSystemClient,
        audio_extractor: AudioExtractor,
        asr_client: AliyunASRClient,
        status_manager: StatusManager,
        output_dir: str = "data/output",
        temp_dir: str = "data/temp"
    ):
        """初始化视频处理器

        Args:
            filesystem_client: file-system-go 客户端
            audio_extractor: 音频提取器
            asr_client: ASR 客户端
            status_manager: 状态管理器
            output_dir: 输出目录
            temp_dir: 临时目录
        """
        self.filesystem_client = filesystem_client
        self.audio_extractor = audio_extractor
        self.asr_client = asr_client
        self.status_manager = status_manager
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)

        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("视频处理器初始化完成")

    async def process_all(self) -> dict:
        """处理所有视频

        Returns:
            处理结果统计
        """
        logger.info("开始处理所有视频")

        # 获取视频列表
        videos = await self.filesystem_client.get_video_list()

        if not videos:
            logger.warning("没有找到视频文件")
            return {
                "total": 0,
                "processed": 0,
                "success": 0,
                "failed": 0
            }

        logger.info(f"找到 {len(videos)} 个视频文件")

        # 统计结果
        total = len(videos)
        processed = 0
        success = 0
        failed = 0

        # 逐个处理视频
        for video in videos:
            # 检查是否已处理
            if await self.status_manager.is_completed(video.aweme_id):
                logger.info(f"视频已处理，跳过: {video.aweme_id}")
                processed += 1
                success += 1
                continue

            # 处理视频
            result = await self.process_video(video)

            processed += 1
            if result.success:
                success += 1
            else:
                failed += 1

        summary = {
            "total": total,
            "processed": processed,
            "success": success,
            "failed": failed
        }

        logger.info(
            f"处理完成: 总计 {total} 个，"
            f"成功 {success} 个，"
            f"失败 {failed} 个"
        )

        return summary

    async def process_video(self, video) -> ProcessResult:
        """处理单个视频

        Args:
            video: 视频信息

        Returns:
            处理结果
        """
        aweme_id = video.aweme_id
        start_time = time.time()

        logger.info(f"开始处理视频: {aweme_id}")

        try:
            # 标记为处理中
            await self.status_manager.mark_processing(aweme_id)

            # 步骤1：下载视频
            video_path = await self.filesystem_client.download_video(
                aweme_id,
                str(self.temp_dir)
            )

            if not video_path:
                error = "视频下载失败"
                await self.status_manager.mark_failed(aweme_id, error)
                return ProcessResult(
                    aweme_id=aweme_id,
                    success=False,
                    error_message=error
                )

            # 步骤2：提取音频
            audio_path = await self.audio_extractor.extract_from_file(
                video_path,
                "wav"
            )

            if not audio_path:
                error = "音频提取失败"
                await self.status_manager.mark_failed(aweme_id, error)
                # 清理视频文件
                delete_file(video_path)
                return ProcessResult(
                    aweme_id=aweme_id,
                    success=False,
                    error_message=error
                )

            # 步骤3：获取音频 URL（用于 ASR）
            audio_url = await self.filesystem_client.get_video_url(aweme_id)
            audio_url = audio_url.replace(".mp4", ".wav")  # 假设音频 URL 格式

            # 步骤4：ASR 识别
            transcript = await self.asr_client.transcribe_file(
                audio_path,
                audio_url
            )

            # 步骤5：保存结果
            if transcript:
                await self._save_result(aweme_id, transcript)
                await self.status_manager.mark_completed(aweme_id)

                process_time = time.time() - start_time
                logger.info(
                    f"视频处理成功: {aweme_id} "
                    f"(耗时 {process_time:.2f} 秒)"
                )

                # 清理临时文件
                delete_file(video_path)
                delete_file(audio_path)

                return ProcessResult(
                    aweme_id=aweme_id,
                    success=True,
                    transcript=transcript,
                    process_time=process_time
                )
            else:
                error = "ASR 识别失败"
                await self.status_manager.mark_failed(aweme_id, error)
                # 清理临时文件
                delete_file(video_path)
                delete_file(audio_path)

                return ProcessResult(
                    aweme_id=aweme_id,
                    success=False,
                    error_message=error
                )

        except Exception as e:
            error = f"处理异常: {e}"
            logger.error(f"视频处理失败: {aweme_id} - {error}")
            await self.status_manager.mark_failed(aweme_id, error)

            return ProcessResult(
                aweme_id=aweme_id,
                success=False,
                error_message=error
            )

    async def _save_result(
        self,
        aweme_id: str,
        transcript: TranscriptResult
    ):
        """保存识别结果

        Args:
            aweme_id: 视频 ID
            transcript: 识别结果
        """
        output_file = self.output_dir / f"{aweme_id}.json"

        # 构建输出数据
        output_data = {
            "aweme_id": aweme_id,
            "text": transcript.text,
            "segments": [
                {
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "text": seg.text,
                    "confidence": seg.confidence
                }
                for seg in transcript.segments
            ],
            "confidence": transcript.confidence,
            "audio_duration": transcript.audio_duration
        }

        # 保存为 JSON 文件
        save_json(output_data, str(output_file))

        logger.info(f"识别结果已保存: {output_file}")
