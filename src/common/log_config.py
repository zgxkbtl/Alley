import logging

def configure_logger(name):
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(filename)s:%(lineno)d - %(levelname)s - %(message)s', 
        datefmt='%m-%d %H:%M:%S'
        )
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
