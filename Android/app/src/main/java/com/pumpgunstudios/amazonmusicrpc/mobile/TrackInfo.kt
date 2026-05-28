package com.pumpgunstudios.amazonmusicrpc.mobile

data class TrackInfo(
    val title: String,
    val artist: String?,
    val album: String?,
    val packageName: String,
    val playbackState: Int?,
    val durationMs: Long?,
    val positionMs: Long?,
    val durationSource: String?,
    val positionSource: String?,
    val artworkUri: String?,
    val artworkSource: String?,
    val lookupSource: String?,
    val lookupAlbum: String?,
    val updatedAtMs: Long,
) {
    val stableKey: String
        get() = listOf(title, artist.orEmpty(), album.orEmpty(), packageName, playbackState?.toString().orEmpty(), artworkUri.orEmpty()).joinToString("|")

    val hasArtwork: Boolean
        get() = artworkSource != null

    val hasDiscordArtwork: Boolean
        get() = artworkUri?.startsWith("http://", true) == true || artworkUri?.startsWith("https://", true) == true

    val hasTimeBar: Boolean
        get() = durationMs != null && durationMs > 0 && positionMs != null && positionMs >= 0

    fun withLookup(lookup: LookupResult): TrackInfo {
        val lookupArt = lookup.artworkUrl.takeIf { it.isNotBlank() }
        val currentHttpArt = artworkUri?.takeIf { it.startsWith("http://", true) || it.startsWith("https://", true) }
        val resolvedDuration = durationMs ?: lookup.durationMs
        return copy(
            album = album?.takeIf { it.isNotBlank() } ?: lookup.album.takeIf { it.isNotBlank() },
            durationMs = resolvedDuration,
            durationSource = durationSource ?: if (lookup.durationMs != null) lookup.source else null,
            artworkUri = currentHttpArt ?: lookupArt ?: artworkUri,
            artworkSource = when {
                currentHttpArt != null -> artworkSource
                lookupArt != null -> lookup.source
                else -> artworkSource
            },
            lookupSource = lookup.source.takeIf { !lookup.isEmpty },
            lookupAlbum = lookup.album.takeIf { it.isNotBlank() },
        )
    }
}
