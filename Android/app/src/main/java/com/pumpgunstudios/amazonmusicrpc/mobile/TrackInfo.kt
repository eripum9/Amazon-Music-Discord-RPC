package com.pumpgunstudios.amazonmusicrpc.mobile

data class TrackInfo(
    val title: String,
    val artist: String?,
    val album: String?,
    val packageName: String,
    val playbackState: Int?,
    val durationMs: Long?,
    val positionMs: Long?,
    val updatedAtMs: Long,
) {
    val stableKey: String
        get() = listOf(title, artist.orEmpty(), album.orEmpty(), packageName, playbackState?.toString().orEmpty()).joinToString("|")
}
