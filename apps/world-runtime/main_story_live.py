from __future__ import annotations

# Production composition order matters:
# main_cognitive_live builds the current public/API stack first; importing the
# interaction story runtime afterwards interposes only the confirmed audience
# consequence boundary used by TikTok, YouTube and the Manager simulator.
import main_cognitive_live
import interaction_story_runtime  # noqa: F401  # side-effect composition


app = main_cognitive_live.app
