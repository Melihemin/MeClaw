from meclaw.tools.base import ToolContext, ToolRegistry
from meclaw.tools.documents import DOCUMENT_TOOLS
from meclaw.tools.files import FILE_TOOLS
from meclaw.tools.utils import UTIL_TOOLS
from meclaw.tools.web import WEB_TOOLS


def build_registry(ctx: ToolContext) -> ToolRegistry:
    specs = [*FILE_TOOLS, *DOCUMENT_TOOLS, *UTIL_TOOLS]
    if ctx.internet:
        specs.extend(WEB_TOOLS)
    return ToolRegistry(ctx, specs)
