"""
FastAPI 服务器
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.server.endpoints import router, set_processor
from src.processor.filesystem_client import FileSystemClient
from src.processor.audio_extractor import AudioExtractor
from src.processor.asr_client import AliyunASRClient
from src.processor.status_manager import StatusManager
from src.processor.video_processor import VideoProcessor
from src.utils import load_config, setup_logger


# 加载配置
config = load_config("config/app.yaml")

# 设置日志
log_config = config.get("app", {}).get("logging", {})
setup_logger(
    log_dir=log_config.get("dir", "logs"),
    level=log_config.get("level", "INFO")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("初始化视频处理器...")

    app_config = config.get("app", {})

    # 初始化各组件
    filesystem_config = app_config.get("filesystem", {})
    filesystem_client = FileSystemClient(
        base_url=filesystem_config.get("base_url", ""),
        query_endpoint=filesystem_config.get("query_endpoint", "/api/videos/query"),
        download_endpoint_template=filesystem_config.get("download_endpoint_template", "/api/videos/{id}/download"),
        timeout=filesystem_config.get("timeout", 300)
    )

    audio_config = app_config.get("audio", {})
    audio_extractor = AudioExtractor(
        cache_dir=app_config.get("files", {}).get("temp_dir", "data/temp"),
        sample_rate=audio_config.get("sample_rate", 16000),
        channels=audio_config.get("channels", 1)
    )

    asr_config = app_config.get("asr", {})
    asr_client = AliyunASRClient(
        api_key=os.getenv(asr_config.get("access_key", ""), ""),
        model=asr_config.get("model", "fun-asr")
    )

    files_config = app_config.get("files", {})
    status_manager = StatusManager(
        status_file=files_config.get("status_file", "data/status.json")
    )

    video_processor = VideoProcessor(
        filesystem_client=filesystem_client,
        audio_extractor=audio_extractor,
        asr_client=asr_client,
        status_manager=status_manager,
        output_dir=files_config.get("output_dir", "data/output"),
        temp_dir=files_config.get("temp_dir", "data/temp")
    )

    # 设置到全局
    set_processor(video_processor)
    app.state.processor = video_processor

    logger.info("视频处理器初始化完成")

    yield

    # 关闭时清理
    logger.info("清理资源...")


# 创建 FastAPI 应用
server_config = config.get("app", {}).get("server", {})
app = FastAPI(
    title="douyin-processor",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "douyin-processor",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8093)

    uvicorn.run(
        "src.server.main:app",
        host=host,
        port=port,
        log_level="info"
    )
