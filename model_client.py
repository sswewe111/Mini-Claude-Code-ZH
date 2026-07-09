from typing import Optional

from utils.logger_handler import logger


def create_model(base_url: Optional[str], api_key: str):
    """创建 OpenAI SDK 客户端；具体环境变量读取由 agent_loop.py 负责。"""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        logger.error("缺少 openai 依赖，无法创建模型客户端")
        raise RuntimeError("缺少依赖 openai，请先安装 requirements.txt。") from exc

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
