import logging
from contextvars import ContextVar


_request_id = ContextVar("barrelboss_request_id", default="-")


def bind_request_id(value):
    return _request_id.set(value or "-")


def release_request_id(token):
    _request_id.reset(token)


def get_request_id():
    return _request_id.get("-")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        return True
