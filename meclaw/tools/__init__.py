from meclaw.tools.base import ToolContext, ToolRegistry
from meclaw.tools.files import FILE_TOOLS


def build_registry(ctx: ToolContext) -> ToolRegistry:
    return ToolRegistry(ctx, [*FILE_TOOLS])
