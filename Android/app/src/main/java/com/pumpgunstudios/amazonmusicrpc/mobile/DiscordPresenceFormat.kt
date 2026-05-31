package com.pumpgunstudios.amazonmusicrpc.mobile

object DiscordPresenceFormat {
    fun assetText(albumName: String?, title: String?): String {
        val album = albumName.orEmpty().trim()
        if (album.length >= 2) return album.take(128)
        if (album.isNotEmpty()) return "Album: $album".take(128)
        val track = title.orEmpty().trim()
        if (track.length >= 2) return track.take(128)
        if (track.isNotEmpty()) return "Track: $track".take(128)
        return "Unknown Album"
    }

    fun timestamps(track: TrackInfo): Pair<Long, Long>? {
        return PlaybackTimeline.timestamps(track.updatedAtMs, track.positionMs, track.durationMs)
    }
}
