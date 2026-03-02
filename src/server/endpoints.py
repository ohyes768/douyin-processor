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
    is_read: bool = False
    read_at: Optional[int] = None


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
    is_read: bool = False
    read_at: Optional[int] = None


class StatsResponse(BaseModel):
    """统计信息响应"""
    total: int
    completed: int
    processing: int
    failed: int
    pending: int
    success_rate: float


class MarkReadRequest(BaseModel):
    """标记已读请求"""
    is_read: bool


class ActionResponse(BaseModel):
    """操作响应"""
    success: bool
    message: str


@router.post("/api/process/async", response_model=TaskResponse)
async def process_videos_async():
    """异步处理所有音频（立即返回，后台处理）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("接收到异步处理请求")

    try:
        # 获取音频列表（带缓存）
        videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
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
        all_statuses = await processor.status_manager.get_all_statuses()
        for video in videos:
            status_data = all_statuses.get(video.aweme_id, {})
            status = status_data.get("status")
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
    status: Optional[str] = Query(None, description="状态筛选: completed/processing/failed/pending"),
    is_read: Optional[bool] = Query(None, description="已读状态筛选")
):
    """获取视频列表（支持分页和状态筛选）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"获取视频列表: page={page}, page_size={page_size}, status={status}, is_read={is_read}")

    try:
        # 获取所有视频（使用缓存）
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )

        # 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        # 第一遍：快速筛选（只读内存数据）
        candidate_videos = []
        for video in all_videos:
            aweme_id = video.aweme_id
            status_data = all_statuses.get(aweme_id, {})
            video_status = status_data.get("status", "pending")
            video_is_read = status_data.get("is_read", False)

            # 默认过滤掉 pending 状态的视频
            if video_status == "pending":
                continue

            # 状态筛选
            if status and video_status != status:
                continue

            # 已读状态筛选
            if is_read is not None and video_is_read != is_read:
                continue

            candidate_videos.append({
                "aweme_id": aweme_id,
                "status": video_status,
                "is_read": video_is_read,
                "audio_url": video.url,
                "status_data": status_data
            })

        # 按上传时间倒序排序（先读取 upload_time）
        for v in candidate_videos:
            aweme_id = v["aweme_id"]
            # 尝试从 output 文件读取 upload_time
            result_file = processor.output_dir / f"{aweme_id}.json"
            if result_file.exists():
                try:
                    result_data = load_json(str(result_file))
                    v["upload_time"] = result_data.get("upload_time", "")
                except:
                    v["upload_time"] = ""
            else:
                v["upload_time"] = ""

        # 分成两组：有时间的和没时间的
        with_time = [v for v in candidate_videos if v["upload_time"]]
        without_time = [v for v in candidate_videos if not v["upload_time"]]

        # 有时间的按时间倒序
        with_time.sort(key=lambda x: x["upload_time"], reverse=True)
        # 没时间的按 ID 倒序
        without_time.sort(key=lambda x: x["aweme_id"], reverse=True)

        # 合并
        candidate_videos = with_time + without_time

        # 分页处理
        total_count = len(candidate_videos)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_videos = candidate_videos[start_idx:end_idx]

        # 只读取当前页需要的文件数据
        video_list = []
        for v in page_videos:
            aweme_id = v["aweme_id"]
            video_status = v["status"]
            status_data = v["status_data"]

            # 默认值
            metadata = {"title": "", "author": "", "description": "", "upload_time": None}
            transcript = None
            processed_at = None
            read_at = None

            # 读取转写结果（仅已完成且有结果文件）
            if video_status == "completed":
                result_file = processor.output_dir / f"{aweme_id}.json"
                if result_file.exists():
                    result_data = load_json(str(result_file))

                    # 从结果文件获取 metadata（优先）
                    if result_data.get("title"):
                        metadata = {
                            "title": result_data.get("title", ""),
                            "author": result_data.get("author", ""),
                            "description": result_data.get("description", ""),
                            "upload_time": result_data.get("upload_time")
                        }

                    transcript = TranscriptInfo(
                        text=result_data.get("text", ""),
                        segments=result_data.get("segments"),
                        confidence=result_data.get("confidence", 0.0),
                        audio_duration=result_data.get("audio_duration", 0.0)
                    )

                    # 从状态文件获取处理时间
                    processed_at_str = status_data.get("updated_at", "")
                    if processed_at_str:
                        try:
                            processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                        except:
                            pass

            # 如果结果文件没有 metadata，从 file-system-go 获取
            if not metadata["title"]:
                md = await processor.filesystem_client.get_video_metadata(aweme_id)
                if md:
                    metadata = {
                        "title": md.title,
                        "author": md.author,
                        "description": md.description,
                        "upload_time": md.upload_time
                    }

            # 获取已读时间
            read_at_str = status_data.get("read_at")
            if read_at_str:
                try:
                    read_at = int(datetime.fromisoformat(read_at_str).timestamp())
                except:
                    pass

            video_list.append(VideoListItem(
                aweme_id=aweme_id,
                status=video_status,
                title=metadata.get("title", ""),
                author=metadata.get("author", ""),
                audio_url=v["audio_url"],
                transcript=transcript,
                processed_at=processed_at,
                upload_time=metadata.get("upload_time"),
                is_read=v["is_read"],
                read_at=read_at
            ))

        return VideoListResponse(
            total_count=total_count,
            videos=video_list,
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

        # 获取已读状态
        is_read = status_data.get("is_read", False)
        read_at = None
        read_at_str = status_data.get("read_at")
        if read_at_str:
            try:
                read_at = int(datetime.fromisoformat(read_at_str).timestamp())
            except:
                pass

        # 获取音频 URL（使用缓存）
        videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )
        audio_url = ""
        for video in videos:
            if video.aweme_id == aweme_id:
                audio_url = video.url
                break

        # 读取转写结果和 metadata（仅已完成）
        transcript = None
        processed_at = None
        error = None
        title = ""
        author = ""
        description = ""
        upload_time = None

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
                # 从结果文件获取 metadata（优先）
                title = result_data.get("title", "")
                author = result_data.get("author", "")
                description = result_data.get("description", "")
                upload_time = result_data.get("upload_time")

                # 获取处理时间
                processed_at_str = status_data.get("updated_at", "")
                if processed_at_str:
                    try:
                        processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                    except:
                        pass
        elif video_status == "failed":
            error = status_data.get("error", "未知错误")

        # 如果结果文件没有 metadata，从 file-system-go 获取
        if not title:
            metadata = await processor.filesystem_client.get_video_metadata(aweme_id)
            if metadata:
                title = metadata.title
                author = metadata.author
                description = metadata.description
                upload_time = metadata.upload_time

        return VideoDetailResponse(
            aweme_id=aweme_id,
            status=video_status,
            title=title,
            author=author,
            description=description,
            audio_url=audio_url,
            transcript=transcript,
            processed_at=processed_at,
            upload_time=upload_time,
            error=error,
            is_read=is_read,
            read_at=read_at
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
        # 从 file-system-go 获取所有视频列表（带缓存）
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )

        # 从 status_manager 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        # 统计各状态数量
        completed = 0
        processing = 0
        failed = 0
        pending = 0

        # 遍历所有实际视频，判断其处理状态
        for video in all_videos:
            aweme_id = video.aweme_id
            status_data = all_statuses.get(aweme_id, {})
            status = status_data.get("status", "pending")

            if status == "completed":
                completed += 1
            elif status == "processing":
                processing += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1

        # 计算总数
        total = len(all_videos)

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


@router.post("/api/videos/{aweme_id}/read", response_model=ActionResponse)
async def mark_video_read(aweme_id: str, request: MarkReadRequest):
    """标记视频已读/未读"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"标记视频已读状态: {aweme_id}, is_read={request.is_read}")

    try:
        await processor.status_manager.mark_read(aweme_id, request.is_read)
        return ActionResponse(
            success=True,
            message=f"已{'标记已读' if request.is_read else '标记未读'}"
        )
    except Exception as e:
        logger.error(f"标记已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/videos/{aweme_id}", response_model=ActionResponse)
async def delete_video(aweme_id: str):
    """硬删除视频（无法恢复）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"删除视频: {aweme_id}")

    try:
        # 从状态文件中移除
        await processor.status_manager.hard_delete(aweme_id)

        # 删除结果文件（如果存在）
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"
        if result_file.exists():
            result_file.unlink()
            logger.info(f"已删除结果文件: {result_file}")

        return ActionResponse(
            success=True,
            message="视频已删除"
        )
    except Exception as e:
        logger.error(f"删除视频失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
