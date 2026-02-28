"""
API 接口端点
"""

import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
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


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "processor_ready": processor is not None
    }
