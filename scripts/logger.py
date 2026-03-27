"""
日志系统 - 捕获所有控制台和文件输出
包括stdout, stderr和训练进度
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
import io


class TeeOutput:
    """双重输出类：同时输出到控制台和日志"""
    
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level
        self.console = sys.stdout
        self.buffer = io.StringIO()
        
    def write(self, message):
        """写入消息到控制台和日志"""
        if message and message.strip():
            # 输出到控制台
            self.console.write(message)
            self.console.flush()
            
            # 输出到日志（去除多余的空白）
            clean_msg = message.strip()
            if clean_msg:
                self.logger.log(self.level, clean_msg)
    
    def flush(self):
        """刷新缓冲区"""
        self.console.flush()
    
    def isatty(self):
        """检查是否是终端"""
        return self.console.isatty()


class Logger:
    """完整日志类：捕获所有输出"""
    
    def __init__(self, name, log_dir="logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"{name}_{timestamp}.log"
        
        # 配置日志
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        
        # 文件处理器 - 详细格式
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
        
        # 重定向stdout和stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = TeeOutput(self.logger, logging.INFO)
        sys.stderr = TeeOutput(self.logger, logging.ERROR)
        
        # 记录启动信息
        self.start_time = datetime.now()
        self._log_header()
    
    def _log_header(self):
        """记录日志头部"""
        self.logger.info("=" * 80)
        self.logger.info(f"训练开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"日志文件: {self.log_file.name}")
        self.logger.info("=" * 80)
    
    def info(self, message):
        """记录信息"""
        self.logger.info(message)
    
    def warning(self, message):
        """记录警告"""
        self.logger.warning(message)
    
    def error(self, message):
        """记录错误"""
        self.logger.error(message)
    
    def separator(self, char="=", length=80):
        """分隔线"""
        self.logger.info(char * length)
    
    def section(self, title):
        """章节标题"""
        self.separator("=", 80)
        self.logger.info(f" {title}")
        self.separator("=", 80)
    
    def get_log_file(self):
        """获取日志文件路径"""
        return self.log_file
    
    def log_elapsed_time(self):
        """记录已用时间"""
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(elapsed.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.logger.info(f"总用时: {hours}小时 {minutes}分 {seconds}秒")
    
    def restore_stdout(self):
        """恢复原始stdout"""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr


# 全局日志实例
_global_logger = None

def get_logger(name="training", log_dir="logs"):
    """获取日志实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger(name, log_dir)
    return _global_logger
