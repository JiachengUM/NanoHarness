from rich import print

from aicore.tools.convert import tool

@tool("web_search")  # Custom name
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"


def test_tool_basic():
    print(search)
    print(search.model_dump())


if __name__ == "__main__":
    test_tool_basic()