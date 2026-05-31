package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.math.max
import kotlin.math.min

object PlaybackTimeline {
    const val STATE_PLAYING = 3

    fun accuratePositionMs(
        basePositionMs: Long,
        playbackState: Int,
        lastUpdateMs: Long,
        playbackSpeed: Float,
        durationMs: Long?,
        nowMs: Long,
    ): Long? {
        if (basePositionMs < 0) return null
        val adjusted = if (playbackState == STATE_PLAYING && lastUpdateMs > 0) {
            basePositionMs + ((nowMs - lastUpdateMs) * playbackSpeed).toLong()
        } else {
            basePositionMs
        }
        val safe = max(0L, adjusted)
        return if (durationMs != null) min(durationMs, safe) else safe
    }

    fun hasTimeBar(durationMs: Long?, positionMs: Long?): Boolean {
        return durationMs != null && durationMs > 0 && positionMs != null && positionMs >= 0
    }

    fun timestamps(updatedAtMs: Long, positionMs: Long?, durationMs: Long?): Pair<Long, Long>? {
        if (!hasTimeBar(durationMs, positionMs)) return null
        val start = updatedAtMs - (positionMs ?: 0L)
        return start to start + (durationMs ?: 0L)
    }
}
