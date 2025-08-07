import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    return logging.getLogger("belgededektif")

def log_file_operation(op_type, file_type, status, message):
    logging.info(f"[{op_type}] {file_type} - {status}: {message}")

def log_azure_operation(op_type, service, status, message):
    logging.info(f"[{op_type}] {service} - {status}: {message}")

def log_api_request(path, method, client_ip, user_agent):
    logging.info(f"API {method} {path} from {client_ip} - {user_agent}")

def log_performance(action, ms, extra=""):
    logging.info(f"{action} - {ms:.2f}ms {extra}")
