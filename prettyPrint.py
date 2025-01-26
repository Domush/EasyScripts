import builtins

COLORS = {
    "info": "\033[94m",  # Light blue
    "warning": "\033[93m",  # Yellow
    "error": "\033[91m",  # Light red
    "success": "\033[92m",  # Green
}
END_COLOR = "\033[0m"

original_print = builtins.print


def print(*args, **kwargs):
    msg_type = kwargs.pop("type", None)
    text = " ".join(str(arg) for arg in args)

    if msg_type and msg_type in COLORS:
        text = f"{COLORS[msg_type]}{text}{END_COLOR}"

    original_print(text, **kwargs)


builtins.print = print
