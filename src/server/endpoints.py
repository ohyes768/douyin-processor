"""
API 接口端点
"""

import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
from loguru import logger

from src.utils import load_json

router = APIRouter()

# 全局处理器引用（在 main.py 中设置）
processor = None


def set_processor(proc):
    """设置处理器实例"""
    global processor
    processor = proc


class ProcessResponse(BaseModel):
    """处理响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class ResultResponse(BaseModel):
    """结果响应"""
    success: bool
    data: Optional[dict] = None


class TaskResponse(BaseModel):
    """任务响应"""
    success: bool
    message: str
    data: Optional[dict] = None


# 新增响应模型
class TranscriptInfo(BaseModel):
    """转写信息"""
    text: str
    segments: Optional[List[dict]] = None
    confidence: float
    audio_duration: float


class VideoListItem(BaseModel):
    """视频列表项"""
    aweme_id: str
    status: str
    title: str
    author: str
    audio_url: str
    transcript: Optional[TranscriptInfo] = None
    processed_at: Optional[int] = None
    upload_time: Optional[str] = None


class VideoListResponse(BaseModel):
    """视频列表响应"""
    total_count: int
    videos: List[VideoListItem]
    page: int
    page_size: int


class VideoDetailResponse(BaseModel):
    """视频详情响应"""
    aweme_id: str
    status: str
    title: str
    author: str
    description: str
    audio_url: str
    transcript: Optional[TranscriptInfo] = None
    processed_at: Optional[int] = None
    upload_time: Optional[str] = None
    error: Optional[str] = None


class StatsResponse(BaseModel):
    """统计信息响应"""
    total: int
    completed: int
    processing: int
    failed: int
    pending: int
    success_rate: float


@router.post("/api/process/async", response_model=TaskResponse)
async def process_videos_async():
    """异步处理所有音频（立即返回，后台处理）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("接收到异步处理请求")

    try:
        # 获取音频列表统计
        videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"}
        )

        if not videos:
            return TaskResponse(
                success=True,
                message="没有待处理的音频",
                data={"total": 0, "pending": 0}
            )

        # 统计待处理数量
        pending_count = 0
        skip_count = 0
        for video in videos:
            status = await processor.status_manager.get_status(video.aweme_id)
            if status is None:
                pending_count += 1
            else:
                skip_count += 1

        # 创建后台任务
        asyncio.create_task(processor.process_all())

        return TaskResponse(
            success=True,
            message="后台处理任务已启动",
            data={
                "total": len(videos),
                "pending": pending_count,
                "skip": skip_count
            }
        )

    except Exception as e:
        logger.error(f"启动异步任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/process", response_model=ProcessResponse)
async def process_videos():
    """同步处理所有音频（等待处理完成）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("接收到处理请求")

    try:
        # 同步处理（等待完成）
        summary = await processor.process_all()

        return ProcessResponse(
            success=True,
            message="处理完成",
            data=summary
        )

    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos/{aweme_id}/result", response_model=ResultResponse)
async def get_video_result(aweme_id: str):
    """获取视频处理结果"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"查询视频结果: {aweme_id}")

    try:
        # 检查状态
        status = await processor.status_manager.get_status(aweme_id)

        if status is None:
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "pending",
                    "message": "视频尚未处理"
                }
            )

        if status == "processing":
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "processing",
                    "message": "视频正在处理中"
                }
            )

        if status == "failed":
            all_statuses = await processor.status_manager.get_all_statuses()
            error = all_statuses.get(aweme_id, {}).get("error", "未知错误")
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "failed",
                    "error": error
                }
            )

        # 已完成，读取结果文件
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"

        if not result_file.exists():
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "completed",
                    "message": "结果文件不存在"
                }
            )

        result_data = load_json(str(result_file))
        result_data["status"] = "completed"

        return ResultResponse(
            success=True,
            data=result_data
        )

    except Exception as e:
        logger.error(f"查询结果失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos", response_model=VideoListResponse)
async def get_videos(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选: completed/processing/failed/pending")
):
    """获取视频列表（支持分页和状态筛选）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"获取视频列表: page={page}, page_size={page_size}, status={status}")

    try:
        # 获取所有视频
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"}
        )

        # 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        # 构建视频列表
        video_list = []

        for video in all_videos:
            aweme_id = video.aweme_id

            # 获取状态
            video_status = all_statuses.get(aweme_id, {}).get("status", "pending")

            # 状态筛选
            if status and video_status != status:
                continue

            # 获取元数据
            metadata = await processor.filesystem_client.get_video_metadata(aweme_id)

            # 读取转写结果（仅已完成且有结果文件）
            transcript = None
            processed_at = None

            if video_status == "completed":
                result_file = processor.output_dir / f"{aweme_id}.json"
                if result_file.exists():
                    result_data = load_json(str(result_file))
                    transcript = TranscriptInfo(
                        text=result_data.get("text", ""),
                        segments=result_data.get("segments"),
                        confidence=result_data.get("confidence", 0.0),
                        audio_duration=result_data.get("audio_duration", 0.0)
                    )
                    # 从状态文件获取处理时间
                    processed_at_str = all_statuses.get(aweme_id, {}).get("updated_at", "")
                    if processed_at_str:
                        try:
                            processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                        except:
                            pass

            video_list.append(VideoListItem(
                aweme_id=aweme_id,
                status=video_status,
                title=metadata.title if metadata else "",
                author=metadata.author if metadata else "",
                audio_url=video.url,
                transcript=transcript,
                processed_at=processed_at,
                upload_time=metadata.upload_time if metadata else None
            ))

        # 分页处理
        total_count = len(video_list)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_videos = video_list[start_idx:end_idx]

        return VideoListResponse(
            total_count=total_count,
            videos=paginated_videos,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"获取视频列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos/{aweme_id}", response_model=VideoDetailResponse)
async def get_video_detail(aweme_id: str):
    """获取单个视频详情"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"获取视频详情: {aweme_id}")

    try:
        # 获取状态
        status = await processor.status_manager.get_status(aweme_id)
        video_status = status if status else "pending"

        # 获取所有状态（用于获取详细信息和错误信息）
        all_statuses = await processor.status_manager.get_all_statuses()
        status_data = all_statuses.get(aweme_id, {})

        # 获取元数据
        metadata = await processor.filesystem_client.get_video_metadata(aweme_id)

        # 获取音频 URL
        videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"}
        )
        audio_url = ""
        for video in videos:
            if video.aweme_id == aweme_id:
                audio_url = video.url
                break

        # 读取转写结果（仅已完成）
        transcript = None
        processed_at = None
        error = None

        if video_status == "completed":
            result_file = processor.output_dir / f"{aweme_id}.json"
            if result_file.exists():
                result_data = load_json(str(result_file))
                transcript = TranscriptInfo(
                    text=result_data.get("text", ""),
                    segments=result_data.get("segments"),
                    confidence=result_data.get("confidence", 0.0),
                    audio_duration=result_data.get("audio_duration", 0.0)
                )
                # 获取处理时间
                processed_at_str = status_data.get("updated_at", "")
                if processed_at_str:
                    try:
                        processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                    except:
                        pass
        elif video_status == "failed":
            error = status_data.get("error", "未知错误")

        return VideoDetailResponse(
            aweme_id=aweme_id,
            status=video_status,
            title=metadata.title if metadata else "",
            author=metadata.author if metadata else "",
            description=metadata.description if metadata else "",
            audio_url=audio_url,
            transcript=transcript,
            processed_at=processed_at,
            upload_time=metadata.upload_time if metadata else None,
            error=error
        )

    except Exception as e:
        logger.error(f"获取视频详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """获取处理统计信息"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("获取统计信息")

    try:
        # 获取所有视频
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"}
        )

        total = len(all_videos)

        # 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        completed = 0
        processing = 0
        failed = 0
        pending = 0

        for video in all_videos:
            status = all_statuses.get(video.aweme_id, {}).get("status", "pending")

            if status == "completed":
                completed += 1
            elif status == "processing":
                processing += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1

        # 计算成功率
        success_rate = 0.0
        if completed + failed > 0:
            success_rate = round(completed / (completed + failed), 2)

        return StatsResponse(
            total=total,
            completed=completed,
            processing=processing,
            failed=failed,
            pending=pending,
            success_rate=success_rate
        )

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "processor_ready": processor is not None
    }
