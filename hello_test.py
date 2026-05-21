def say_hello(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}! จาก Coder-Alpha"


def add(a: int | float, b: int | float) -> int | float:
    """Return the sum of a and b."""
    return a + b


if __name__ == "__main__":
    print(say_hello("คุณ Ball"))