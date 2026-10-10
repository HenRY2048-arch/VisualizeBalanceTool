"""VisualizeBalance 入口点"""

import logging
import sys


def _setup_logging() -> None:
    """配置日志"""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    _setup_logging()

    # 延迟导入，确保日志已初始化
    from .app import App

    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
