import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging():
    """Gelişmiş logging yapılandırması"""
    
    # Logs klasörünü oluştur
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Log formatı
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # Ana logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    
    # File handler - Genel loglar
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, 'app.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    
    # Error handler - Sadece hatalar
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, 'errors.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(log_format)
    logger.addHandler(error_handler)
    
    # API işlemleri için özel handler
    api_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, 'api_operations.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    api_handler.setLevel(logging.INFO)
    api_handler.setFormatter(log_format)
    
    # API logger
    api_logger = logging.getLogger('api_operations')
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.INFO)
    
    return logger

def get_api_logger():
    """API işlemleri için özel logger"""
    return logging.getLogger('api_operations')

def log_file_operation(operation: str, filename: str, status: str, details: str = ""):
    """Dosya işlemlerini logla"""
    api_logger = get_api_logger()
    api_logger.info(f"FILE_OP | {operation} | {filename} | {status} | {details}")

def log_azure_operation(operation: str, service: str, status: str, details: str = ""):
    """Azure işlemlerini logla"""
    api_logger = get_api_logger()
    api_logger.info(f"AZURE_OP | {operation} | {service} | {status} | {details}")

def log_api_request(endpoint: str, method: str, client_ip: str, user_agent: str = ""):
    """API isteklerini logla"""
    api_logger = get_api_logger()
    api_logger.info(f"API_REQ | {method} | {endpoint} | {client_ip} | {user_agent}")

def log_performance(operation: str, duration_ms: float, details: str = ""):
    """Performans metriklerini logla"""
    api_logger = get_api_logger()
    api_logger.info(f"PERF | {operation} | {duration_ms:.2f}ms | {details}")

