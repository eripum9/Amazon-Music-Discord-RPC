package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PlaybackTimelineTest {
    @Test
    fun adjustsPlayingPositionAndClampsToDuration() {
        val position = PlaybackTimeline.accuratePositionMs(
            basePositionMs = 5000L,
            playbackState = PlaybackTimeline.STATE_PLAYING,
            lastUpdateMs = 1000L,
            playbackSpeed = 1f,
            durationMs = 10000L,
            nowMs = 8000L,
        )
        assertEquals(10000L, position)
    }

    @Test
    fun keepsPausedPositionStable() {
        val position = PlaybackTimeline.accuratePositionMs(
            basePositionMs = 5000L,
            playbackState = 2,
            lastUpdateMs = 1000L,
            playbackSpeed = 1f,
            durationMs = 10000L,
            nowMs = 8000L,
        )
        assertEquals(5000L, position)
    }

    @Test
    fun rejectsInvalidPositionAndDetectsTimeBar() {
        assertNull(PlaybackTimeline.accuratePositionMs(-1L, PlaybackTimeline.STATE_PLAYING, 1000L, 1f, 10000L, 2000L))
        assertTrue(PlaybackTimeline.hasTimeBar(10000L, 0L))
        assertFalse(PlaybackTimeline.hasTimeBar(null, 0L))
        assertFalse(PlaybackTimeline.hasTimeBar(10000L, null))
    }

    @Test
    fun createsDiscordTimestampBounds() {
        assertEquals(8000L to 18000L, PlaybackTimeline.timestamps(10000L, 2000L, 10000L))
        assertNull(PlaybackTimeline.timestamps(10000L, null, 10000L))
    }
}
