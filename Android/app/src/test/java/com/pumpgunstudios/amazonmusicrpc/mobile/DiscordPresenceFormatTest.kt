package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals

class DiscordPresenceFormatTest {
    @Test
    fun labelsShortAlbumAndTrackNames() {
        assertEquals("Album: A", DiscordPresenceFormat.assetText("A", "Song"))
        assertEquals("Track: A", DiscordPresenceFormat.assetText("", "A"))
        assertEquals("Unknown Album", DiscordPresenceFormat.assetText("", ""))
        assertEquals("Wolf", DiscordPresenceFormat.assetText("Wolf", "Rusty"))
    }

    @Test
    fun createsPresenceTimestampsFromTrackTimeBar() {
        val track = trackInfo(positionMs = 60000L, durationMs = 180000L, updatedAtMs = 100000L)
        assertEquals(40000L to 220000L, DiscordPresenceFormat.timestamps(track))
    }
}
