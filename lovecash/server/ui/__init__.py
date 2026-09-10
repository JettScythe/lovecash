"""Self-contained, zero-build HTML pages served by the relay."""

from lovecash.server.ui.dashboard import DASHBOARD_HTML
from lovecash.server.ui.overlay import OVERLAY_HTML, render_overlay
from lovecash.server.ui.tip import TIP_HTML

__all__ = ["DASHBOARD_HTML", "OVERLAY_HTML", "TIP_HTML", "render_overlay"]
