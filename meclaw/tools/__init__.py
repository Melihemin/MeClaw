from meclaw.tools.base import ToolContext, ToolRegistry
from meclaw.tools.documents import DOCUMENT_TOOLS
from meclaw.tools.files import FILE_TOOLS
from meclaw.tools.utils import UTIL_TOOLS


def build_registry(ctx: ToolContext) -> ToolRegistry:
    return ToolRegistry(ctx, [*FILE_TOOLS, *DOCUMENT_TOOLS, *UTIL_TOOLS])
