#!/usr/bin/env python3
"""Apply the plane-scaled overscan change to a KWin source tree.

    port.py /path/to/kwin-source

KWin already has an "overscan" setting per output, but only offers it when the
graphics driver has a connector property for it. This edit makes the DRM
backend fall back to scaling the planes into a smaller, centred area of the
screen, so the setting also works on drivers without that property (Intel,
NVIDIA). With the fallback, an overscan of N means the picture shrinks by N
percent in each dimension, capped at 25.

Written as anchored edits instead of a fixed patch because distributions ship
different KWin versions. Known to apply to 6.3.6, 6.7.x and 6.8.2. It stops
with an error, changing nothing, if the source does not look as expected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = "usesPlaneScaledOverscan"


class PortError(Exception):
    pass


def replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise PortError(f"{what}: expected exactly one match, found {text.count(old)}")
    return text.replace(old, new)


def port_output(text: str) -> str:
    text = replace_once(
        text,
        """    if (m_connector->overscan.isValid() || m_connector->underscan.isValid()) {
        capabilities |= Capability::Overscan;
    }""",
        """    if (m_connector->overscan.isValid() || m_connector->underscan.isValid()) {
        capabilities |= Capability::Overscan;
    } else if (m_gpu->atomicModeSetting() && !m_connector->isInternal()) {
        // No connector property for it (e.g. Intel, NVIDIA): the pipeline
        // scales the planes into a smaller area of the screen instead
        capabilities |= Capability::Overscan;
    }""",
        "drm_output.cpp capability check",
    )

    # Plane-scaled overscan only shows up with the next frame, so ask for one
    # when the value changes.
    start = text.find("void DrmOutput::applyQueuedChanges(")
    if start < 0:
        raise PortError("drm_output.cpp: applyQueuedChanges() not found")
    anchor = "    m_pipeline->applyPendingChanges();\n"
    at = text.find(anchor, start)
    if at < 0 or at - start > 600:
        raise PortError("drm_output.cpp: applyPendingChanges() call not found in applyQueuedChanges()")
    at += len(anchor)
    return (
        text[:at]
        + """    if (m_pipeline->overscan() != m_state.overscan) {
        // plane-scaled overscan only takes effect with the next frame
        m_renderLoop->scheduleRepaint();
    }
"""
        + text[at:]
    )


def port_pipeline_header(text: str, rect: str) -> str:
    return replace_once(
        text,
        "    void setOverscan(uint32_t overscan);\n",
        f"""    void setOverscan(uint32_t overscan);
    /**
     * Whether overscan compensation has to be done by scaling planes,
     * because the connector has no property for it
     */
    bool usesPlaneScaledOverscan() const;
    /**
     * Maps the target rect of a plane into the area of the screen that is
     * left when compensating for overscan by scaling planes
     */
    {rect} applyPlaneScaledOverscan(const {rect} &target, bool isCursor, const QPointF &hotspot) const;
""",
        "drm_pipeline.h setOverscan declaration",
    )


FUNCTIONS = """// With plane scaling, the "overscan" setting is the percentage by which the
// picture shrinks in each dimension. More than this is never useful
static constexpr uint32_t s_maxPlaneScaledOverscan = 25;

bool DrmPipeline::usesPlaneScaledOverscan() const
{
    return m_pending.overscan != 0
        && m_pending.mode
        && gpu()->atomicModeSetting()
        && !m_connector->overscan.isValid()
        && !m_connector->underscan.isValid();
}

RECT DrmPipeline::applyPlaneScaledOverscan(const RECT &target, bool isCursor, const QPointF &hotspot) const
{
    if (!usesPlaneScaledOverscan()) {
        return target;
    }
    const QSize modeSize = m_pending.mode->size();
    if (modeSize.isEmpty()) {
        return target;
    }
    const double factor = 1.0 - std::min(m_pending.overscan, s_maxPlaneScaledOverscan) / 100.0;
    // keep the sizes even, and the picture centered
    const int areaWidth = int(std::round(modeSize.width() * factor)) & ~1;
    const int areaHeight = int(std::round(modeSize.height() * factor)) & ~1;
    const int areaX = (modeSize.width() - areaWidth) / 2;
    const int areaY = (modeSize.height() - areaHeight) / 2;
    const double scaleX = areaWidth / double(modeSize.width());
    const double scaleY = areaHeight / double(modeSize.height());

    if (isCursor) {
        // Cursor planes usually can't scale: keep the size of the sprite,
        // and move it so that its hotspot ends up in the right place
        const int x = areaX + int(std::round((target.x() + hotspot.x()) * scaleX - hotspot.x()));
        const int y = areaY + int(std::round((target.y() + hotspot.y()) * scaleY - hotspot.y()));
        return RECT(x, y, target.width(), target.height());
    }

    const int x1 = areaX + int(std::round(target.x() * scaleX));
    const int y1 = areaY + int(std::round(target.y() * scaleY));
    const int x2 = areaX + int(std::round((target.x() + target.width()) * scaleX));
    const int y2 = areaY + int(std::round((target.y() + target.height()) * scaleY));
    return RECT(x1, y1, x2 - x1, y2 - y1);
}

"""


def port_pipeline(text: str, rect: str) -> str:
    generic = "plane->set(commit, layer->sourceRect().toRect(), layer->targetRect());"
    old_primary = "primary->set(commit, m_primaryLayer->sourceRect().toRect(), m_primaryLayer->targetRect());"

    if "OutputLayerType::CursorOnly" in text or old_primary not in text:
        # 6.7 and later: one function sets up every plane.
        text = replace_once(
            text,
            generic,
            "plane->set(commit, layer->sourceRect().toRect(), applyPlaneScaledOverscan("
            "layer->targetRect(), layer->type() == OutputLayerType::CursorOnly, layer->hotspot()));",
            "drm_pipeline.cpp plane setup",
        )
    else:
        # 6.3: the primary and the cursor plane are set up separately.
        text = replace_once(
            text,
            old_primary,
            "primary->set(commit, m_primaryLayer->sourceRect().toRect(), "
            "applyPlaneScaledOverscan(m_primaryLayer->targetRect(), false, QPointF()));",
            "drm_pipeline.cpp primary plane setup",
        )
        text = replace_once(
            text,
            generic,
            "plane->set(commit, layer->sourceRect().toRect(), "
            "applyPlaneScaledOverscan(layer->targetRect(), true, layer->hotspot()));",
            "drm_pipeline.cpp cursor plane setup",
        )

    text = replace_once(
        text,
        "void DrmPipeline::setOverscan(uint32_t overscan)\n",
        FUNCTIONS.replace("RECT", rect) + "void DrmPipeline::setOverscan(uint32_t overscan)\n",
        "drm_pipeline.cpp setOverscan definition",
    )
    return replace_once(
        text,
        "#include <errno.h>\n",
        "#include <algorithm>\n#include <cmath>\n#include <errno.h>\n",
        "drm_pipeline.cpp includes",
    )


def port(source: Path) -> None:
    drm = source / "src" / "backends" / "drm"
    files = {name: drm / name for name in ("drm_output.cpp", "drm_pipeline.h", "drm_pipeline.cpp", "drm_plane.h")}
    for path in files.values():
        if not path.is_file():
            raise PortError(f"{path} not found: is this a KWin source tree?")

    texts = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    if MARKER in texts["drm_pipeline.h"]:
        print("port.py: already applied, nothing to do")
        return

    # Newer KWin has its own Rect class; older versions use QRect.
    match = re.search(r"void set\(DrmAtomicCommit \*commit, const (\w+) &src, const (\w+) &dst\);", texts["drm_plane.h"])
    if not match:
        raise PortError("drm_plane.h: DrmPlane::set() not found")
    rect = match.group(2)

    # Work everything out before writing, so a failure leaves the tree untouched.
    result = {
        "drm_output.cpp": port_output(texts["drm_output.cpp"]),
        "drm_pipeline.h": port_pipeline_header(texts["drm_pipeline.h"], rect),
        "drm_pipeline.cpp": port_pipeline(texts["drm_pipeline.cpp"], rect),
    }
    for name, text in result.items():
        files[name].write_text(text, encoding="utf-8")
    print(f"port.py: applied plane-scaled overscan (rect type {rect})")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        port(Path(sys.argv[1]))
    except PortError as error:
        print(f"port.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
