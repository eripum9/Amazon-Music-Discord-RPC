# MIT License - Copyright (c) 2026 eripum9

class CommandController:
    def __init__(self, handlers):
        self._handlers = {str(name).strip().lower(): handler for name, handler in dict(handlers or {}).items() if callable(handler)}

    @property
    def commands(self):
        return tuple(sorted(self._handlers))

    def dispatch(self, command):
        name = str(command or "").strip().lower()
        handler = self._handlers.get(name)
        if not handler:
            return False
        handler()
        return True
