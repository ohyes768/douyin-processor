"""
API 接口端点
"""

from fastapi import APIRouter, HTTPException
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


@router.post("/api/process", response_model=ProcessResponse)
async def process_videos():
    """处理所有视频"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("接收到处理请求")

    try:
        # 异步处理（在后台执行）
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
